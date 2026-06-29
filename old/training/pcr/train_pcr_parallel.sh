#!/bin/bash
#
# Parallel PCR Training Orchestrator
# Distributes PCR training across multiple machines via SSH
#
# Workflow:
#   1. Check available machines
#   2. Partition grid into equal-sized chunks for each machine
#   3. Prepare data files on head node (pre-process CFD + sensor data)
#   4. Deploy data files and training script to each machine
#   5. Launch training on all machines in parallel
#   6. Collect coefficient files back to head node
#
# Usage: train_pcr_parallel.sh <sensor_folder> <simulations_dir> <num_machines>
#                              [nx] [ny] [nz]

set -e

log_info() { echo "[INFO] $(date '+%H:%M:%S') $1"; }
log_warn() { echo "[WARN] $(date '+%H:%M:%S') $1"; }
log_error() { echo "[ERROR] $(date '+%H:%M:%S') $1" >&2; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$SCRIPT_DIR"

# Load grid configuration from grid_config.json
source "${SCRIPT_DIR}/read_grid_config.sh"

# Activate conda environment (required for Python scripts)
# Don't source bashrc - it may have 'return' for non-interactive shells
# Instead, directly initialize conda
for conda_path in \
    "$HOME/miniforge3/etc/profile.d/conda.sh" \
    "$HOME/miniconda3/etc/profile.d/conda.sh" \
    "$HOME/anaconda3/etc/profile.d/conda.sh" \
    "/local/home/$USER/miniforge3/etc/profile.d/conda.sh"; do
    if [ -f "$conda_path" ]; then
        source "$conda_path" 2>/dev/null || true
        break
    fi
done
if command -v conda &> /dev/null; then
    conda activate cfdai_intheloop 2>/dev/null || conda activate base 2>/dev/null || true
fi

# SSH Configuration
SSH_KEY_PATH="${WORK_DIR}/id_rsa"
SSH_OPTIONS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -i ${SSH_KEY_PATH}"
MACHINE_LIST_FILE="${WORK_DIR}/machine_list.txt"

# Remote user
REMOTE_USER="$(whoami)"

# Timing
SCRIPT_START_TIME=$(date +%s)

################################################################################
# Machine Management
################################################################################

parse_machine_list() {
    local machine_list=()
    local machine_names=()
    
    if [ ! -f "$MACHINE_LIST_FILE" ]; then
        log_error "Machine list file not found: $MACHINE_LIST_FILE"
        return 1
    fi
    
    while IFS=' ' read -r name ip; do
        [[ -z "$name" || "$name" =~ ^# ]] && continue
        machine_list+=("$ip")
        machine_names+=("$name")
    done < "$MACHINE_LIST_FILE"
    
    MACHINES=("${machine_list[@]}")
    MACHINE_NAMES=("${machine_names[@]}")
}

verify_ssh_key() {
    if [ ! -f "$SSH_KEY_PATH" ]; then
        log_error "SSH key not found: $SSH_KEY_PATH"
        return 1
    fi
    
    local perms=$(stat -c %a "$SSH_KEY_PATH")
    if [ "$perms" != "600" ]; then
        log_warn "SSH key has incorrect permissions ($perms). Fixing to 600..."
        chmod 600 "$SSH_KEY_PATH"
    fi
    return 0
}

test_machine_connectivity() {
    local machine=$1
    local machine_name=$2
    
    if ssh $SSH_OPTIONS "$REMOTE_USER@$machine" "echo ok" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

################################################################################
# Deployment Functions
################################################################################

deploy_to_machine() {
    local machine=$1
    local machine_id=$2
    local data_file=$3
    local remote_work_dir="$WORK_DIR"
    local deploy_start=$(date +%s.%N)
    
    log_info "  [M$machine_id] Deploying data and scripts..."
    
    # Get file size for throughput calculation
    local file_size_bytes=$(stat -c%s "$data_file" 2>/dev/null || echo "0")
    local file_size_mb=$(echo "scale=2; $file_size_bytes / 1048576" | bc)
    
    # Create remote directories and clean up old output files from previous runs
    local mkdir_start=$(date +%s.%N)
    ssh $SSH_OPTIONS "$REMOTE_USER@$machine" "
        mkdir -p '$remote_work_dir/pcr_data' '$remote_work_dir/pcr_output/machine_$machine_id'
        # Clean up old coefficient files from previous runs to prevent mixing
        rm -f '$remote_work_dir/pcr_output/machine_$machine_id'/pcr_coefficients_*.csv 2>/dev/null || true
    " || {
        log_error "  [M$machine_id] Failed to create remote directories"
        return 1
    }
    local mkdir_end=$(date +%s.%N)
    
    # Copy data file (main upload)
    local upload_start=$(date +%s.%N)
    scp $SSH_OPTIONS "$data_file" "$REMOTE_USER@$machine:$remote_work_dir/pcr_data/" || {
        log_error "  [M$machine_id] Failed to copy data file"
        return 1
    }
    local upload_end=$(date +%s.%N)
    local upload_time=$(echo "$upload_end - $upload_start" | bc)
    local upload_speed=$(echo "scale=1; $file_size_mb / $upload_time" | bc 2>/dev/null || echo "N/A")
    
    # Copy training script
    scp $SSH_OPTIONS "$WORK_DIR/train_pcr_chunk.py" "$REMOTE_USER@$machine:$remote_work_dir/" || {
        log_error "  [M$machine_id] Failed to copy training script"
        return 1
    }
    
    # Copy PCR binary (required for training)
    local pcr_binary="$WORK_DIR/training2/pcr"
    if [[ -f "$pcr_binary" ]]; then
        scp $SSH_OPTIONS "$pcr_binary" "$REMOTE_USER@$machine:$remote_work_dir/" || {
            log_error "  [M$machine_id] Failed to copy pcr binary"
            return 1
        }
        # Make binary executable
        ssh $SSH_OPTIONS "$REMOTE_USER@$machine" "chmod +x '$remote_work_dir/pcr'" || {
            log_error "  [M$machine_id] Failed to make pcr binary executable"
            return 1
        }
    else
        log_error "  [M$machine_id] PCR binary not found at $pcr_binary"
        return 1
    fi
    
    local deploy_end=$(date +%s.%N)
    local total_time=$(echo "$deploy_end - $deploy_start" | bc)
    log_info "  [M$machine_id] ✓ Deployed ${file_size_mb}MB in ${upload_time}s (${upload_speed} MB/s)"
    return 0
}

################################################################################
# Training Functions
################################################################################

launch_training_on_machine() {
    local machine=$1
    local machine_id=$2
    local data_file_name=$3
    local output_log=$4
    local remote_work_dir="$WORK_DIR"
    local status_file="$DISTRIBUTED_DIR/status_$machine_id"
    local pid_file="$DISTRIBUTED_DIR/pid_$machine_id"
    
    # Launch entire SSH session in background immediately
    # The script is already deployed during Phase 4
    {
        ssh $SSH_OPTIONS "$REMOTE_USER@$machine" "
            source ~/.bashrc 2>/dev/null || true
            
            # Initialize conda
            for conda_path in \
                \"\\\$HOME/miniforge3/etc/profile.d/conda.sh\" \
                \"\\\$HOME/miniconda3/etc/profile.d/conda.sh\" \
                \"\\\$HOME/anaconda3/etc/profile.d/conda.sh\" \
                \"/local/home/\\\$USER/miniforge3/etc/profile.d/conda.sh\"; do
                if [ -f \"\\\$conda_path\" ]; then
                    source \"\\\$conda_path\" 2>/dev/null || true
                    break
                fi
            done
            
            conda activate cfdai_intheloop 2>/dev/null || conda activate base 2>/dev/null || true
            
            cd '$remote_work_dir'
            python3 train_pcr_chunk.py 'pcr_data/$data_file_name' 'pcr_output/machine_$machine_id'
        " > "$output_log" 2>&1
        echo $? > "$status_file"
    } &
    
    # Capture PID and write to file
    echo $! > "$pid_file"
}

# Helper to get PID after launch
get_training_pid() {
    local machine_id=$1
    local pid_file="$DISTRIBUTED_DIR/pid_$machine_id"
    if [ -f "$pid_file" ]; then
        cat "$pid_file"
    else
        echo "0"
    fi
}

collect_results_from_machine() {
    local machine=$1
    local machine_id=$2
    local local_output_dir=$3
    local remote_work_dir="$WORK_DIR"
    local collect_start=$(date +%s.%N)
    
    log_info "  [M$machine_id] Collecting coefficient files..."
    
    mkdir -p "$local_output_dir/machine_$machine_id"
    
    # Copy coefficient files back with timing
    local download_start=$(date +%s.%N)
    rsync -a \
        -e "ssh $SSH_OPTIONS" \
        "$REMOTE_USER@$machine:$remote_work_dir/pcr_output/machine_$machine_id/" \
        "$local_output_dir/machine_$machine_id/" \
        || {
        log_warn "  [M$machine_id] Issues collecting results"
        return 1
    }
    local download_end=$(date +%s.%N)
    local download_time=$(echo "$download_end - $download_start" | bc)
    
    local file_count=$(find "$local_output_dir/machine_$machine_id" -name "pcr_coefficients_*.csv" 2>/dev/null | wc -l)
    local dir_size=$(du -sh "$local_output_dir/machine_$machine_id" 2>/dev/null | cut -f1 || echo "N/A")
    
    log_info "  [M$machine_id] ✓ Collected $file_count files (${dir_size}) in ${download_time}s"
    return 0
}

################################################################################
# Main Script
################################################################################

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <sensor_folder> <simulations_dir> <num_machines> [nx] [ny] [nz]"
    echo ""
    echo "Arguments:"
    echo "  sensor_folder       Path to folder containing sensor_out.csv"
    echo "  simulations_dir     Path to folder containing simulation CSVs"
    echo "  num_machines        Number of machines to use"
    echo "  nx                  Grid points in X (default: ${GRID_NX} from grid_config.json)"
    echo "  ny                  Grid points in Y (default: ${GRID_NY} from grid_config.json)"
    echo "  nz                  Grid points in Z (default: ${GRID_NZ} from grid_config.json)"
    exit 1
fi

SENSOR_FOLDER="$1"
SIMULATIONS_DIR="$2"
NUM_MACHINES_REQUESTED="$3"
NX="${4:-$GRID_NX}"
NY="${5:-$GRID_NY}"
NZ="${6:-$GRID_NZ}"  # From grid_config.json

# Validate inputs
if [ ! -d "$SENSOR_FOLDER" ]; then
    log_error "Sensor folder not found: $SENSOR_FOLDER"
    exit 1
fi

if [ ! -d "$SIMULATIONS_DIR" ]; then
    log_error "Simulations folder not found: $SIMULATIONS_DIR"
    exit 1
fi

# Setup directories
RUN_ID="$(date +%s)"
DISTRIBUTED_DIR="${WORK_DIR}/pcr_distributed_${RUN_ID}"
DATA_PREP_DIR="${DISTRIBUTED_DIR}/prepared_data"
OUTPUT_DIR="${DISTRIBUTED_DIR}/output"
LOGS_DIR="${DISTRIBUTED_DIR}/logs"
FINAL_OUTPUT_DIR="${WORK_DIR}/training/data"

mkdir -p "$DATA_PREP_DIR" "$OUTPUT_DIR" "$LOGS_DIR" "$FINAL_OUTPUT_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║         DISTRIBUTED PCR TRAINING ORCHESTRATOR                    ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
log_info "Configuration:"
log_info "  Sensor folder: $SENSOR_FOLDER"
log_info "  Simulations folder: $SIMULATIONS_DIR"
log_info "  Grid dimensions: ${NX}x${NY}x${NZ} = $((NX * NY * NZ)) total points"
log_info "  Machines requested: $NUM_MACHINES_REQUESTED"
log_info "  Working directory: $DISTRIBUTED_DIR"
echo ""

# Print grid information table
print_grid_info() {
    local nx=$1
    local ny=$2
    local nz=$3
    
    # Grid boundaries from grid_config.json (loaded via read_grid_config.sh)
    local X_MIN=$GRID_X_MIN
    local X_MAX=$GRID_X_MAX
    local Y_MIN=$GRID_Y_MIN
    local Y_MAX=$GRID_Y_MAX
    local Z_MIN=$GRID_Z_MIN
    local Z_MAX=$GRID_Z_MAX
    
    # Calculate ranges and resolutions
    local x_range=$(echo "$X_MAX - $X_MIN" | bc)
    local y_range=$(echo "$Y_MAX - $Y_MIN" | bc)
    local z_range=$(echo "$Z_MAX - $Z_MIN" | bc)
    
    local x_res=$(echo "scale=1; $x_range / ($nx - 1)" | bc)
    local y_res=$(echo "scale=1; $y_range / ($ny - 1)" | bc)
    local z_res=$(echo "scale=1; $z_range / ($nz - 1)" | bc)
    
    local total_points=$((nx * ny * nz))
    
    echo "┌─────────────────────────────────────────────────────────────────────┐"
    echo "│                         GRID INFORMATION                            │"
    echo "├──────────┬──────────┬──────────┬────────────┬────────────┬──────────┤"
    echo "│   Axis   │  Min (m) │  Max (m) │ Range (m)  │ Grid Points│ Res. (m) │"
    echo "├──────────┼──────────┼──────────┼────────────┼────────────┼──────────┤"
    printf "│    X     │  %7.1f │  %7.1f │   %7.1f   │     %4d   │   ~%4.1f  │\n" $X_MIN $X_MAX $x_range $nx $x_res
    printf "│    Y     │  %7.1f │  %7.1f │   %7.1f   │     %4d   │   ~%4.1f  │\n" $Y_MIN $Y_MAX $y_range $ny $y_res
    printf "│    Z     │  %7.1f │  %7.1f │   %7.1f   │     %4d   │   ~%4.1f  │\n" $Z_MIN $Z_MAX $z_range $nz $z_res
    echo "├──────────┴──────────┴──────────┴────────────┴────────────┴──────────┤"
    printf "│  Total: %d points  |  Domain: %.0f×%.0f×%.0f m³                        │\n" $total_points $x_range $y_range $z_range
    echo "└─────────────────────────────────────────────────────────────────────┘"
}

print_grid_info $NX $NY $NZ
echo ""

################################################################################
# Phase 1: Check Available Machines
################################################################################
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  PHASE 1: MACHINE DISCOVERY                                      │"
echo "└──────────────────────────────────────────────────────────────────┘"

verify_ssh_key || exit 1
parse_machine_list || exit 1

log_info "Testing connectivity to ${#MACHINES[@]} machines in parallel..."

# Test machines in parallel to avoid SSH rate limiting timeouts
TEMP_MACHINE_FILE=$(mktemp)
TEMP_NAMES_FILE=$(mktemp)

local -a _conn_pids=()
for i in "${!MACHINES[@]}"; do
    (
        if ssh $SSH_OPTIONS "$REMOTE_USER@${MACHINES[$i]}" "echo ok" &>/dev/null 2>&1; then
            echo "${MACHINES[$i]}" >> "$TEMP_MACHINE_FILE"
            echo "${MACHINE_NAMES[$i]}" >> "$TEMP_NAMES_FILE"
            echo "  ✓ ${MACHINE_NAMES[$i]} (${MACHINES[$i]})"
        else
            echo "  ✗ ${MACHINE_NAMES[$i]} (${MACHINES[$i]}) - unreachable"
        fi
    ) &
    _conn_pids+=($!)
done
for _conn_pid in "${_conn_pids[@]}"; do
    wait "$_conn_pid" 2>/dev/null || true
done

# Read results into arrays
AVAILABLE_MACHINES=()
AVAILABLE_NAMES=()
while IFS= read -r machine; do
    AVAILABLE_MACHINES+=("$machine")
done < "$TEMP_MACHINE_FILE"
while IFS= read -r name; do
    AVAILABLE_NAMES+=("$name")
done < "$TEMP_NAMES_FILE"
rm -f "$TEMP_MACHINE_FILE" "$TEMP_NAMES_FILE"

NUM_AVAILABLE=${#AVAILABLE_MACHINES[@]}

if [ "$NUM_AVAILABLE" -eq 0 ]; then
    log_error "No machines are accessible!"
    exit 1
fi

# Limit to requested number or available
if [ $NUM_AVAILABLE -gt $NUM_MACHINES_REQUESTED ]; then
    AVAILABLE_MACHINES=("${AVAILABLE_MACHINES[@]:0:$NUM_MACHINES_REQUESTED}")
    AVAILABLE_NAMES=("${AVAILABLE_NAMES[@]:0:$NUM_MACHINES_REQUESTED}")
    NUM_AVAILABLE=$NUM_MACHINES_REQUESTED
fi

echo ""
log_info "Using $NUM_AVAILABLE machines for distributed training"
echo ""

################################################################################
# Phase 2: Partition Grid
################################################################################
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  PHASE 2: GRID PARTITIONING                                      │"
echo "└──────────────────────────────────────────────────────────────────┘"

cd "$WORK_DIR"

log_info "Partitioning $((NX * NY * NZ)) grid points across $NUM_AVAILABLE machines..."
echo ""

python3 partition_pcr_grid.py "$NUM_AVAILABLE" "$NX" "$NY" "$NZ" || {
    log_error "Failed to partition grid"
    exit 1
}

# Move partition files to working directory
mv pcr_partitions.json "$DISTRIBUTED_DIR/"
mv pcr_partitions_full.json "$DISTRIBUTED_DIR/"

# Create grid_index.csv upfront (before training starts)
log_info "Creating grid_index.csv from partition data..."
GRID_INDEX_FROM_PARTITIONS="${WORK_DIR}/create_grid_index_from_partitions.py"
if [ -f "$GRID_INDEX_FROM_PARTITIONS" ]; then
    python3 "$GRID_INDEX_FROM_PARTITIONS" \
        "$DISTRIBUTED_DIR/pcr_partitions_full.json" \
        "$FINAL_OUTPUT_DIR" 2>&1 | while read line; do
        log_info "  $line"
    done
else
    log_warn "create_grid_index_from_partitions.py not found - will create grid_index at the end"
fi

echo ""

################################################################################
# Phase 3: Prepare Data Files
################################################################################
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  PHASE 3: DATA PREPARATION                                       │"
echo "└──────────────────────────────────────────────────────────────────┘"

log_info "Preparing machine-specific data files..."
log_info "  This pre-computes CFD lookups for each grid point to minimize data transfer"

PREP_START=$(date +%s)

# Debug: verify conda environment and python
log_info "DEBUG: Python path: $(which python3)"
log_info "DEBUG: Python version: $(python3 --version 2>&1)"
log_info "DEBUG: Current dir: $(pwd)"
log_info "DEBUG: Calling prepare_pcr_data.py..."

python3 prepare_pcr_data.py \
    "$SENSOR_FOLDER" \
    "$SIMULATIONS_DIR" \
    "$DISTRIBUTED_DIR/pcr_partitions_full.json" \
    "$DATA_PREP_DIR" || {
    log_error "Failed to prepare data files"
    exit 1
}

PREP_END=$(date +%s)
PREP_DURATION=$((PREP_END - PREP_START))

echo ""
log_info "Data preparation completed in ${PREP_DURATION}s"
echo ""

################################################################################
# Phase 4: Deploy to Machines
################################################################################
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  PHASE 4: DEPLOYMENT                                             │"
echo "└──────────────────────────────────────────────────────────────────┘"

log_info "Deploying data and scripts to $NUM_AVAILABLE machines..."
echo ""

DEPLOY_START=$(date +%s)
DEPLOYMENT_FAILED=()

for m in "${!AVAILABLE_MACHINES[@]}"; do
    machine="${AVAILABLE_MACHINES[$m]}"
    machine_name="${AVAILABLE_NAMES[$m]}"
    data_file="$DATA_PREP_DIR/machine_${m}_data.pkl"
    
    if [ ! -f "$data_file" ]; then
        log_warn "  [M$m] Data file not found: $data_file"
        DEPLOYMENT_FAILED+=("$m")
        continue
    fi
    
    if ! deploy_to_machine "$machine" "$m" "$data_file"; then
        DEPLOYMENT_FAILED+=("$m")
    fi
done

DEPLOY_END=$(date +%s)
DEPLOY_DURATION=$((DEPLOY_END - DEPLOY_START))

if [ ${#DEPLOYMENT_FAILED[@]} -gt 0 ]; then
    log_error "Deployment failed on machines: ${DEPLOYMENT_FAILED[*]}"
    exit 1
fi

echo ""
log_info "Deployment completed in ${DEPLOY_DURATION}s"
echo ""

################################################################################
# Phase 5: Launch Training
################################################################################
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  PHASE 5: PARALLEL TRAINING                                      │"
echo "└──────────────────────────────────────────────────────────────────┘"

log_info "Launching training jobs on $NUM_AVAILABLE machines..."
echo ""

# Display expected workload
echo "  Machine Assignments:"
python3 << DISPLAY_PARTITIONS
import json
with open('$DISTRIBUTED_DIR/pcr_partitions.json') as f:
    data = json.load(f)
    for p in data['partitions']:
        mid = p['machine_id']
        pts = p['num_points']
        pct = p['pct_of_total']
        print(f"    Machine {mid}: {pts:,} points ({pct:.1f}%)")
DISPLAY_PARTITIONS
echo ""

TRAIN_START=$(date +%s)

declare -a TRAINING_PIDS
declare -a TRAINING_MACHINES

# Launch all training jobs in parallel (no waiting between launches)
for m in "${!AVAILABLE_MACHINES[@]}"; do
    machine="${AVAILABLE_MACHINES[$m]}"
    data_file_name="machine_${m}_data.pkl"
    output_log="$LOGS_DIR/machine_${m}_training.log"
    
    # This function launches in background and writes PID to file
    launch_training_on_machine "$machine" "$m" "$data_file_name" "$output_log"
done

# Small delay to let all background processes start and write PID files
sleep 0.5

# Collect PIDs and log
for m in "${!AVAILABLE_MACHINES[@]}"; do
    machine="${AVAILABLE_MACHINES[$m]}"
    pid=$(get_training_pid "$m")
    
    TRAINING_PIDS+=("$pid")
    TRAINING_MACHINES+=("$m:$machine")
    
    log_info "  [M$m] Launched (PID: $pid)"
done

echo ""
log_info "All $NUM_AVAILABLE training jobs launched in parallel, waiting for completion..."
echo ""

# Wait for all training jobs
FAILED_MACHINES=()
COMPLETED_COUNT=0

for i in "${!TRAINING_PIDS[@]}"; do
    pid=${TRAINING_PIDS[$i]}
    machine_info=${TRAINING_MACHINES[$i]}
    machine_id="${machine_info%:*}"
    machine="${machine_info#*:}"
    
    # Wait for the wrapper process
    wait $pid 2>/dev/null || true
    
    # Check actual exit status from status file
    status_file="$DISTRIBUTED_DIR/status_$machine_id"
    if [ -f "$status_file" ]; then
        exit_status=$(cat "$status_file" 2>/dev/null || echo "1")
        if [ "$exit_status" = "0" ]; then
            COMPLETED_COUNT=$((COMPLETED_COUNT + 1))
            log_info "  [M$machine_id] ✓ Training completed"
        else
            FAILED_MACHINES+=("$machine_id")
            log_error "  [M$machine_id] ✗ Training failed (exit code: $exit_status)"
        fi
    else
        FAILED_MACHINES+=("$machine_id")
        log_error "  [M$machine_id] ✗ Training failed (no status file)"
    fi
done

TRAIN_END=$(date +%s)
TRAIN_DURATION=$((TRAIN_END - TRAIN_START))

echo ""
log_info "Training phase completed in ${TRAIN_DURATION}s"
log_info "  Successful: $COMPLETED_COUNT / $NUM_AVAILABLE"
echo ""

if [ ${#FAILED_MACHINES[@]} -gt 0 ]; then
    log_error "Training failed on machines: ${FAILED_MACHINES[*]}"
    log_error "Check logs in: $LOGS_DIR/"
    exit 1
fi

################################################################################
# Phase 6: Collect Results
################################################################################
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  PHASE 6: RESULT COLLECTION                                      │"
echo "└──────────────────────────────────────────────────────────────────┘"

log_info "Collecting coefficient files from all machines..."
echo ""

COLLECT_START=$(date +%s)

for m in "${!AVAILABLE_MACHINES[@]}"; do
    machine="${AVAILABLE_MACHINES[$m]}"
    collect_results_from_machine "$machine" "$m" "$OUTPUT_DIR"
done

COLLECT_END=$(date +%s)
COLLECT_DURATION=$((COLLECT_END - COLLECT_START))

echo ""
log_info "Collection completed in ${COLLECT_DURATION}s"
echo ""

################################################################################
# Phase 7: Merge Results
################################################################################
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  PHASE 7: MERGE RESULTS                                          │"
echo "└──────────────────────────────────────────────────────────────────┘"

# FINAL_OUTPUT_DIR already defined at script start

# Clean up any existing coefficient files from previous runs
if [ -d "$FINAL_OUTPUT_DIR" ]; then
    OLD_COUNT=$(find "$FINAL_OUTPUT_DIR" -name "pcr_coefficients_*.csv" 2>/dev/null | wc -l)
    if [ "$OLD_COUNT" -gt 0 ]; then
        log_info "Cleaning up $OLD_COUNT old coefficient files from previous runs..."
        find "$FINAL_OUTPUT_DIR" -name "pcr_coefficients_*.csv" -delete 2>/dev/null || true
        # Remove old grid_index.csv but KEEP grid_index_metadata.json (created in Phase 2)
        rm -f "$FINAL_OUTPUT_DIR/grid_index.csv" 2>/dev/null || true
        log_info "  ✓ Cleanup complete"
    fi
fi

mkdir -p "$FINAL_OUTPUT_DIR"

log_info "Merging coefficient files to: $FINAL_OUTPUT_DIR"

MERGE_COUNT=0
for machine_dir in "$OUTPUT_DIR"/machine_*; do
    if [ -d "$machine_dir" ]; then
        count=$(find "$machine_dir" -name "pcr_coefficients_*.csv" 2>/dev/null | wc -l)
        MERGE_COUNT=$((MERGE_COUNT + count))
        find "$machine_dir" -name "pcr_coefficients_*.csv" -exec cp {} "$FINAL_OUTPUT_DIR"/ \; 2>/dev/null || true
    fi
done

TOTAL_COEFS=$(find "$FINAL_OUTPUT_DIR" -name "pcr_coefficients_*.csv" 2>/dev/null | wc -l)
EXPECTED_COEFS=$((NX * NY * NZ))

echo ""
log_info "Coefficient Summary:"
log_info "  Generated: $TOTAL_COEFS files"
log_info "  Expected:  $EXPECTED_COEFS files"

if [ "$TOTAL_COEFS" -eq "$EXPECTED_COEFS" ]; then
    log_info "  Status: ✓ COMPLETE"
elif [ "$TOTAL_COEFS" -gt "$EXPECTED_COEFS" ]; then
    log_warn "  Status: ⚠ EXTRA FILES ($((TOTAL_COEFS - EXPECTED_COEFS)) more than expected - possible leftover from previous runs)"
else
    log_warn "  Status: ⚠ INCOMPLETE (missing $((EXPECTED_COEFS - TOTAL_COEFS)) files)"
fi

################################################################################
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  PHASE 8: MARK GRID INDEX COMPLETE                               │"
echo "└──────────────────────────────────────────────────────────────────┘"

# Update grid_index metadata to mark training as complete
GRID_INDEX_METADATA="$FINAL_OUTPUT_DIR/grid_index_metadata.json"
if [ -f "$GRID_INDEX_METADATA" ]; then
    log_info "Updating grid_index metadata to mark completion..."
    python3 << UPDATE_METADATA
import json
from datetime import datetime

with open('$GRID_INDEX_METADATA', 'r') as f:
    metadata = json.load(f)

metadata['status'] = 'complete'
metadata['completed_at'] = datetime.now().isoformat()
metadata['coefficient_files_found'] = $TOTAL_COEFS
metadata['coefficient_files_expected'] = $EXPECTED_COEFS

with open('$GRID_INDEX_METADATA', 'w') as f:
    json.dump(metadata, f, indent=2)

print(f"✓ Status updated: {metadata['status']}")
print(f"  Completed at: {metadata['completed_at']}")
print(f"  Files: {metadata['coefficient_files_found']}/{metadata['coefficient_files_expected']}")
UPDATE_METADATA
else
    # Fallback: create grid_index if it doesn't exist (e.g., if Phase 2 script was not available)
    log_warn "grid_index_metadata.json not found - creating grid_index.csv from coefficient files..."
    GRID_INDEX_SCRIPT="${WORK_DIR}/create_grid_index.py"
    if [ -f "$GRID_INDEX_SCRIPT" ]; then
        python "$GRID_INDEX_SCRIPT" "$FINAL_OUTPUT_DIR" 2>&1 | while read line; do
            log_info "  $line"
        done
    fi
fi

# Verify grid_index.csv exists
if [ -f "$FINAL_OUTPUT_DIR/grid_index.csv" ]; then
    GRID_POINTS=$(wc -l < "$FINAL_OUTPUT_DIR/grid_index.csv")
    log_info "  ✓ grid_index.csv: $((GRID_POINTS - 1)) points"
else
    log_warn "  ⚠ grid_index.csv not found in $FINAL_OUTPUT_DIR"
fi

################################################################################
# Summary
################################################################################
SCRIPT_END_TIME=$(date +%s)
TOTAL_DURATION=$((SCRIPT_END_TIME - SCRIPT_START_TIME))
TOTAL_HOURS=$((TOTAL_DURATION / 3600))
TOTAL_MINUTES=$(((TOTAL_DURATION % 3600) / 60))
TOTAL_SECONDS=$((TOTAL_DURATION % 60))

# Calculate throughput
TOTAL_POINTS=$((NX * NY * NZ))
THROUGHPUT=$(echo "scale=1; $TOTAL_POINTS / $TOTAL_DURATION" | bc 2>/dev/null || echo "N/A")

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║         DISTRIBUTED PCR TRAINING COMPLETE                        ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
log_info "Summary:"
log_info "  Machines used:       $NUM_AVAILABLE"
log_info "  Grid points trained: ${TOTAL_POINTS}"
log_info "  Coefficient files:   $TOTAL_COEFS"
log_info "  Throughput:          ${THROUGHPUT} points/second"
log_info "  Output location:     $FINAL_OUTPUT_DIR"
echo ""
log_info "┌─────────────────────────────────────────────────────────────┐"
log_info "│  TIMING BREAKDOWN                                          │"
log_info "├──────────────────────────────┬────────────┬────────────────┤"
log_info "│  Phase                       │   Time (s) │   % of Total   │"
log_info "├──────────────────────────────┼────────────┼────────────────┤"
PREP_PCT=$(echo "scale=1; $PREP_DURATION * 100 / $TOTAL_DURATION" | bc 2>/dev/null || echo "0")
DEPLOY_PCT=$(echo "scale=1; $DEPLOY_DURATION * 100 / $TOTAL_DURATION" | bc 2>/dev/null || echo "0")
TRAIN_PCT=$(echo "scale=1; $TRAIN_DURATION * 100 / $TOTAL_DURATION" | bc 2>/dev/null || echo "0")
COLLECT_PCT=$(echo "scale=1; $COLLECT_DURATION * 100 / $TOTAL_DURATION" | bc 2>/dev/null || echo "0")
log_info "$(printf '│  %-28s │  %8d  │    %6.1f%%     │' 'Data Preparation' $PREP_DURATION $PREP_PCT)"
log_info "$(printf '│  %-28s │  %8d  │    %6.1f%%     │' 'Deployment (upload)' $DEPLOY_DURATION $DEPLOY_PCT)"
log_info "$(printf '│  %-28s │  %8d  │    %6.1f%%     │' 'Training (parallel)' $TRAIN_DURATION $TRAIN_PCT)"
log_info "$(printf '│  %-28s │  %8d  │    %6.1f%%     │' 'Collection (download)' $COLLECT_DURATION $COLLECT_PCT)"
log_info "├──────────────────────────────┼────────────┼────────────────┤"
log_info "$(printf '│  %-28s │  %8d  │    100.0%%     │' 'TOTAL' $TOTAL_DURATION)"
log_info "└──────────────────────────────┴────────────┴────────────────┘"
echo ""
log_info "Formatted Total: ${TOTAL_HOURS}h ${TOTAL_MINUTES}m ${TOTAL_SECONDS}s"
echo ""
log_info "Merged coefficients: $FINAL_OUTPUT_DIR"
echo ""

################################################################################
# Phase 8: Cleanup
################################################################################
log_info "--- Cleanup ---"

# Clean up current run's temporary directory
if [ -d "$DISTRIBUTED_DIR" ]; then
    log_info "Removing temporary directory: $DISTRIBUTED_DIR"
    rm -rf "$DISTRIBUTED_DIR"
fi

# Clean up any old pcr_distributed_* directories (older than current run)
OLD_DIRS=$(find "$WORK_DIR" -maxdepth 1 -type d -name "pcr_distributed_*" 2>/dev/null | wc -l)
if [ "$OLD_DIRS" -gt 0 ]; then
    log_info "Cleaning up $OLD_DIRS old pcr_distributed_* directories..."
    find "$WORK_DIR" -maxdepth 1 -type d -name "pcr_distributed_*" -exec rm -rf {} \; 2>/dev/null || true
    log_info "  ✓ Cleanup complete"
fi

echo ""

# Export for main.sh to pick up
export COEF_OUTPUT_DIR="$FINAL_OUTPUT_DIR"
