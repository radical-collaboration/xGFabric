#!/bin/bash
#
# main.sh - CFDaAI In-the-Loop Pipeline Entry Point
#
# Unified orchestrator for CFD simulations and ML model training.
# Works on both NERSC (SLURM) and UCSB (SSH) clusters.
#
# Usage:
#   ./main.sh [options]
#
# Options:
#   --mode <mode>        Pipeline mode: full, sim-only, train-only (default: full)
#   --system <system>    Force system type: nersc, nd, ucsb, local, hybrid (default: auto)
#   --iterations <n>     Maximum iterations (default: from config)
#   --threads <n>        Number of threads for compute jobs (default: 32)
#   --config <file>      Configuration file (default: config.sh)
#   --workflow_number    Workflow identification number for the coordinator
#   --coord_log_file     Where the coordinator is checking for start/stop
#   --dry-run            Show what would be done without executing
#   --resume             Auto-skip phases if results already exist
#   --start-from <phase> Start from phase: data, simulations, training, evaluation
#   --skip-data          Skip data acquisition phase
#   --skip-simulations   Skip simulations phase
#   --skip-training      Skip training phase
#   --skip-evaluation    Skip evaluation phase
#   --use-data <dir>     Use existing data directory instead of fetching
#   --use-sims <dir>     Use existing simulation results directory
#   --use-sensor <dir>   Use existing sensor data directory (required for pcr)
#   --help               Show this help message

set -eo pipefail

################################################################################
# Script Setup
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export WORK_DIR="$SCRIPT_DIR"

# Compute dynamic user paths (for portability across different users)
export CURRENT_USER="${USER:-$(whoami)}"
export USER_INITIAL="${CURRENT_USER:0:1}"
export USER_HOME="/global/homes/${USER_INITIAL}/${CURRENT_USER}"
export USER_PSCRATCH="/pscratch/sd/${USER_INITIAL}/${CURRENT_USER}"

# Default options
MODE="full"
CONFIG_FILE="${WORK_DIR}/config.sh"
DRY_RUN=false
RESUME_MODE=false
SIMULATION_THREADS=32
START_FROM="data"
SKIP_DATA=false
SKIP_SIMULATIONS=false
SKIP_TRAINING=false
SKIP_EVALUATION=false
USE_DATA_DIR=""
USE_SIMS_DIR=""
USE_SENSOR_DIR=""
USER_TRAIN_MODELS=""

################################################################################
# Parse Arguments
################################################################################

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            MODE="$2"
            shift 2
            ;;
        --system)
            export SYSTEM_TYPE="$2"
            shift 2
            ;;
        --iterations)
            USER_MAX_ITERATIONS="$2"
            shift 2
            ;;
        --threads)
            SIMULATION_THREADS="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --workflow_number)
            export WORKFLOW_NUMBER="$2"
            shift 2
            ;;
        --coord_run_name)
            export COORD_RUN_NAME="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --resume)
            RESUME_MODE=true
            shift
            ;;
        --start-from)
            START_FROM="$2"
            shift 2
            ;;
        --skip-data)
            SKIP_DATA=true
            shift
            ;;
        --skip-simulations)
            SKIP_SIMULATIONS=true
            shift
            ;;
        --skip-training)
            SKIP_TRAINING=true
            shift
            ;;
        --skip-evaluation)
            SKIP_EVALUATION=true
            shift
            ;;
        --use-data)
            USE_DATA_DIR="$(cd "$2" 2>/dev/null && pwd || echo "$2")"
            SKIP_DATA=true
            shift 2
            ;;
        --use-sims|--sim-data)
            USE_SIMS_DIR="$(cd "$2" 2>/dev/null && pwd || echo "$2")"
            if [[ ! -d "$USE_SIMS_DIR" ]]; then
                echo "[ERROR] --use-sims path does not exist: $2"
                exit 1
            fi
            SKIP_SIMULATIONS=true
            shift 2
            ;;
        --use-sensor)
            USE_SENSOR_DIR="$(cd "$2" 2>/dev/null && pwd || echo "$2")"
            if [[ ! -d "$USE_SENSOR_DIR" ]]; then
                echo "[ERROR] --use-sensor path does not exist: $2"
                exit 1
            fi
            shift 2
            ;;
        --models)
            USER_TRAIN_MODELS="$2"
            shift 2
            ;;
        --help|-h)
            grep "^#" "$0" | head -20 | sed 's/^# *//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

################################################################################
# Load Configuration
################################################################################

# Load user config if it exists
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

# Load system libraries
source "${WORK_DIR}/env/system_config.sh"
source "${WORK_DIR}/lib/common.sh"
source "${WORK_DIR}/lib/dispatch.sh"
source "${WORK_DIR}/lib/simulations.sh"
source "${WORK_DIR}/data/data_source.sh"
source "${WORK_DIR}/training/orchestrate_training.sh"

# Initialize system
init_system || {
    echo "ERROR: Failed to initialize system"
    exit 1
}

# Hybrid mode: fail fast if NERSC is required but not reachable.
# This check runs before any pipeline work so we don't discover
# connectivity issues mid-run.
if [[ "${SYSTEM_TYPE:-}" == "hybrid" ]]; then
    validate_hybrid_nersc || {
        echo "ERROR: Hybrid mode NERSC validation failed — aborting"
        exit 1
    }
fi

################################################################################
# Setup
################################################################################

# Set defaults from config (CLI args take precedence over config.sh)
MAX_ITERATIONS="${USER_MAX_ITERATIONS:-${MAX_ITERATIONS:-100}}"
CONVERGENCE_THRESHOLD="${CONVERGENCE_THRESHOLD:-0.01}"
# User CLI --models takes precedence, then env/config, default to pcr
TRAIN_MODELS="${USER_TRAIN_MODELS:-${TRAIN_MODELS:-pcr}}"
if [[ "${SYSTEM_TYPE:-}" == "nersc" ]]; then
    RESULTS_DIR="results/${COORD_RUN_NAME}/workflow_${WORKFLOW_NUMBER}"
    LOGS_DIR="logs/${COORD_RUN_NAME}"
    export SLURM_LOGS_DIR="logs/${COORD_RUN_NAME}"  # NERSC path, created remotely
elif [[ "${SYSTEM_TYPE:-}" == "nd" ]]; then
    RESULTS_DIR="results/${COORD_RUN_NAME}/workflow_${WORKFLOW_NUMBER}"
    LOGS_DIR="logs/${COORD_RUN_NAME}"
else
    RESULTS_DIR="${RESULTS_DIR:-${SCRATCH_DIR:-/local/foam/cases}/results}"
    LOGS_DIR="${LOGS_DIR:-${WORK_DIR}/jobs_logs}"
    export SLURM_LOGS_DIR="${USER_HOME}/jobs_logs"  # NERSC path, created remotely
fi

# Create directories
ensure_dir "$RESULTS_DIR"
ensure_dir "$LOGS_DIR"
# SLURM_LOGS_DIR is on NERSC — only create locally if we're on NERSC
[[ "${SYSTEM_TYPE:-}" == "nersc" ]] && ensure_dir "$SLURM_LOGS_DIR"

# Start logging
LOG_FILE="${LOGS_DIR}/workflows/${WORKFLOW_NUMBER}/pipeline_$(date +%Y%m%d_%H%M%S).log"
LATENCY_LOG="${LOGS_DIR}/workflows/${WORKFLOW_NUMBER}/latency_$(date +%Y%m%d_%H%M%S).log"
export STATUS_FILE="${LOGS_DIR}/coordinator/workflow_status_log.csv"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "workflow_$WORKFLOW_NUMBER,workflow,started,$(date '+%s.%N')" >> "$STATUS_FILE"

# Latency tracking functions
declare -A phase_start_time
declare -A phase_end_time
job_start_time=$(date +%s.%N)

track_phase_start() {
    local phase="$1"
    phase_start_time["$phase"]=$(date +%s.%N)
    log_info "[LATENCY] Starting phase: $phase"
}

track_phase_end() {
    local phase="$1"
    phase_end_time["$phase"]=$(date +%s.%N)
    local duration=$(echo "${phase_end_time[$phase]} - ${phase_start_time[$phase]}" | bc)
    log_info "[LATENCY] Phase complete: $phase (${duration}s)"
    echo "$phase: ${duration}s" >> "$LATENCY_LOG"
}

################################################################################
# Pipeline Banner
################################################################################

log_section "CFDaAI In-the-Loop Pipeline"
log_info "System: ${SYSTEM_TYPE}"
log_info "Mode: ${MODE}"
log_info "Workflow number: ${WORKFLOW_NUMBER}"
log_info "Models: ${TRAIN_MODELS}"
log_info "Results: ${RESULTS_DIR}"
log_info "Log: ${LOG_FILE}"

# Display system information
log_info "Available memory: $(get_available_memory_gb)GB"
log_info "Available disk: $(get_available_disk_gb "$WORK_DIR")GB"
if [[ -n "${DATA_CUTOFF_DATE:-}" ]]; then
    log_info "Data cutoff: ${DATA_CUTOFF_DATE}"
fi

if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY RUN - no actual execution"
fi
if [[ "$RESUME_MODE" == "true" ]]; then
    log_info "Resume mode: will skip phases with existing results"
fi
if [[ "$START_FROM" != "data" ]]; then
    log_info "Starting from: ${START_FROM}"
fi
if [[ -n "$USE_DATA_DIR" ]]; then
    log_info "Using external data: ${USE_DATA_DIR}"
fi
if [[ -n "$USE_SIMS_DIR" ]]; then
    log_info "Using external sims: ${USE_SIMS_DIR}"
fi

################################################################################
# Skip Check Functions
################################################################################

# Check if phase should be skipped
# Args: phase_name results_dir
# Returns: 0 if should skip, 1 if should run
should_skip_phase() {
    local phase="$1"
    local results_dir="$2"
    
    # Check explicit skip flags
    case "$phase" in
        data)
            [[ "$SKIP_DATA" == "true" ]] && return 0
            ;;
        simulations)
            [[ "$SKIP_SIMULATIONS" == "true" ]] && return 0
            ;;
        training)
            [[ "$SKIP_TRAINING" == "true" ]] && return 0
            ;;
        evaluation)
            [[ "$SKIP_EVALUATION" == "true" ]] && return 0
            ;;
    esac
    
    # Check start-from (skip phases before start-from)
    local phase_order=("data" "simulations" "training" "evaluation")
    local start_idx=-1
    local phase_idx=-1
    for i in "${!phase_order[@]}"; do
        [[ "${phase_order[$i]}" == "$START_FROM" ]] && start_idx=$i
        [[ "${phase_order[$i]}" == "$phase" ]] && phase_idx=$i
    done
    if [[ $phase_idx -lt $start_idx ]]; then
        return 0  # Skip phases before start-from
    fi
    
    # In resume mode, check if results exist
    if [[ "$RESUME_MODE" == "true" && -d "$results_dir" ]]; then
        local has_results=false
        case "$phase" in
            data)
                # Check for sensor data CSV
                [[ -n "$(find "$results_dir" -name '*.csv' 2>/dev/null | head -1)" ]] && has_results=true
                ;;
            simulations)
                # Check for postProcess directory
                [[ -n "$(find "$results_dir" -type d -name 'postProcess' 2>/dev/null | head -1)" ]] && has_results=true
                ;;
            training)
                # Check for model files
                [[ -n "$(find "$results_dir" -name '*.pkl' -o -name '*.h5' -o -name '*.pt' 2>/dev/null | head -1)" ]] && has_results=true
                ;;
            evaluation)
                # Check for metrics file
                [[ -f "${results_dir}/sensor_metrics.json" ]] && has_results=true
                ;;
        esac
        if [[ "$has_results" == "true" ]]; then
            return 0  # Skip - results exist
        fi
    fi
    
    return 1  # Don't skip
}

################################################################################
# Pipeline Functions
################################################################################

# Validate that sensor data timestamps are consistent with the cutoff date used.
# Logs the sensor time range and warns if any records pre-date the cutoff.
# Args: sensor_csv_or_txt  cutoff_date_string
_validate_sensor_cutoff() {
    local sensor_file="$1"
    local cutoff="$2"
    python3 "${WORK_DIR}/utils/validate_sensor_cutoff.py" "$sensor_file" "$cutoff"
}

run_simulation_phase() {
    local iteration="$1"
    local sim_output="${RESULTS_DIR}/simulations"
    local param_dir="${RESULTS_DIR}/params"
    
    log_subsection "Simulations - Iteration ${iteration}"
    
    ensure_dir "$sim_output"
    ensure_dir "$param_dir"
    
    # Generate simulation parameters from sensor data
    local data_dir="${RESULTS_DIR}/data"
    if [[ -n "$USE_DATA_DIR" ]]; then
        data_dir="$USE_DATA_DIR"
    fi
    
    local sensor_csv
    sensor_csv=$(find "$data_dir" -name "sensor_out.csv" -o -name "sensor_data.csv" 2>/dev/null | head -1)
    
    local sim_param_mode="${SIM_PARAM_MODE:-interpolated}"
    
    if [[ -n "$sensor_csv" && -f "$sensor_csv" ]]; then
        if [[ -n "${DATA_CUTOFF_DATE:-}" ]]; then
            _validate_sensor_cutoff "$sensor_csv" "${DATA_CUTOFF_DATE}"
        fi
        if [[ "$sim_param_mode" == "sensor_direct" || "$sim_param_mode" == "direct" ]]; then
            # Use actual sensor measurements directly
            log_info "Using direct sensor measurements for simulation parameters"
            local max_sims="${NUM_SIMULATIONS:-50}"
            generate_sim_params_from_sensor "${param_dir}/sim_params.csv" "$sensor_csv" "$max_sims"
        else
            # Default: Extract wind speed range and interpolate
            local ws_stats
            ws_stats=$(python3 "${WORK_DIR}/utils/compute_wind_stats.py" "$sensor_csv" 2>/dev/null || echo "2.0,16.0")
            local ws_min="${ws_stats%%,*}"
            local ws_max="${ws_stats##*,}"
            local num_sims="${NUM_SIMULATIONS:-10}"
            log_info "Wind speed range from sensor data: ${ws_min} - ${ws_max} m/s"
            generate_sim_params "${param_dir}/sim_params.csv" "$ws_min" "$ws_max" "0" "$num_sims"
        fi
    else
        log_warn "No sensor data found, using default wind speed range"
        generate_sim_params "${param_dir}/sim_params.csv" "2.0" "16.0" "0" "10"
    fi
    
    # Run simulations
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would run simulations from: ${param_dir}"
    else
        run_simulations "${param_dir}/sim_params.csv" "$sim_output"
    fi
}

run_training_phase() {
    local iteration="$1"
    local sim_output="${2:-${RESULTS_DIR}/simulations}"
    local data_output="${3:-${RESULTS_DIR}/data}"
    local model_output="${RESULTS_DIR}/models"
    
    log_subsection "Training - Iteration ${iteration}"
    
    ensure_dir "$model_output"
    
    # Set sensor data dir for PCR training
    if [[ -n "$USE_SENSOR_DIR" ]]; then
        export SENSOR_DATA_DIR="$USE_SENSOR_DIR"
    elif [[ -n "$USE_DATA_DIR" ]]; then
        export SENSOR_DATA_DIR="$USE_DATA_DIR"
    else
        export SENSOR_DATA_DIR="$data_output"
    fi
    
    log_info "Using simulation data: ${sim_output}"
    log_info "Using sensor data: ${SENSOR_DATA_DIR}"
    
    # Train each configured model.
    # Hybrid mode: submit all NERSC jobs first, run UCSB jobs, then wait+collect.
    if [[ "$DRY_RUN" == "true" ]]; then
        for model in $TRAIN_MODELS; do
            log_info "[DRY RUN] Would train ${model} model"
        done
    elif [[ "${SYSTEM_TYPE:-}" == "hybrid" ]]; then
        run_training_phase_hybrid "$sim_output" "$model_output"
    else
        for model in $TRAIN_MODELS; do
            run_training "$model" "$sim_output" "${model_output}/${model}"
        done
    fi
}

run_evaluation_phase() {
    local iteration="$1"
    local model_output="${RESULTS_DIR}/models"
    local data_dir="${USE_SENSOR_DIR:-${RESULTS_DIR}/data}"
    local eval_output="${RESULTS_DIR}/evaluation"
    
    log_subsection "Evaluation - Iteration ${iteration}"
    
    ensure_dir "$eval_output"
    
    # Calculate basic sensor data metrics
    local sensor_file
    sensor_file=$(find "$data_dir" -name "sensor_out.csv" -o -name "sensor_data.csv" | head -1)
    
    if [[ -z "$sensor_file" || ! -f "$sensor_file" ]]; then
        log_warn "No sensor data found for evaluation"
        return 0
    fi
    
    log_info "Computing metrics from: ${sensor_file}"

    if [[ -n "${DATA_CUTOFF_DATE:-}" ]]; then
        _validate_sensor_cutoff "$sensor_file" "${DATA_CUTOFF_DATE}"
    fi

    # Use Python to compute simple stats
    python3 "${WORK_DIR}/utils/compute_sensor_metrics.py" "$sensor_file" "$eval_output"
    
    log_info "Evaluation metrics computed"
}

check_convergence() {
    local iteration="$1"
    
    # TODO: Implement convergence check
    # Return 0 if converged, 1 if should continue
    
    # For now, never converge (run all iterations)
    return 1
}

################################################################################
# Main Pipeline
################################################################################

run_full_pipeline() {
    for iteration in $(seq 1 "$MAX_ITERATIONS"); do
        timer_start "pipeline_total"

        log_section "Starting pipeline"
        timer_start "workflow_${WORKFLOW_NUMBER}"
        
        local workflow_dir="${RESULTS_DIR}"
        local data_dir="${workflow_dir}/data"
        local sim_dir="${workflow_dir}/simulations"
        local model_dir="${workflow_dir}/models"
        local eval_dir="${workflow_dir}/evaluation"
        ensure_dir "$workflow_dir"
        
        # Handle external data/sim directories
        if [[ -n "$USE_DATA_DIR" ]]; then
            data_dir="$USE_DATA_DIR"
        fi
        if [[ -n "$USE_SIMS_DIR" ]]; then
            sim_dir="$USE_SIMS_DIR"
        fi
        
        # Phase 1: Fetch data
        log_subsection "Data Acquisition"
        timer_start "data_acquisition"
        if should_skip_phase "data" "$data_dir"; then
            log_info "[SKIP] Data phase - results exist at: ${data_dir}"
        elif [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY RUN] Would fetch sensor data"
        else
            fetch_sensor_data "${workflow_dir}/data" "${DATA_CUTOFF_DATE:-}"
        fi
        timer_end "data_acquisition"
        
        # Phase 2: Run simulations
        log_subsection "Simulations"
        timer_start "simulations"
        start_ram_monitor "OpenFOAM Simulations"
        if should_skip_phase "simulations" "$sim_dir"; then
            log_info "[SKIP] Simulations phase - results exist at: ${sim_dir}"
        elif [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY RUN] Would run simulations"
        else
            run_simulation_phase "$iteration"
            # Wait for all simulation jobs to complete before training
            if [[ "$SYSTEM_TYPE" == "nersc" ]] || [[ "$SYSTEM_TYPE" == "nd" ]]; then
                log_info "Waiting for simulation jobs to complete..."
                wait_for_tasks "simulation"
            fi
        fi
        stop_ram_monitor "OpenFOAM Simulations"
        timer_end "simulations"
        
        # Phase 3: Train models
        log_subsection "Training"
        timer_start "training"
        start_ram_monitor "PCR Training"
        if should_skip_phase "training" "$model_dir"; then
            log_info "[SKIP] Training phase - results exist at: ${model_dir}"
        elif [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY RUN] Would train ${TRAIN_MODELS} model(s)"
        else
            run_training_phase "$iteration" "$sim_dir" "$data_dir"
            # Wait for all training jobs to complete before evaluation
            if [[ "$SYSTEM_TYPE" == "nersc" ]] || [[ "$SYSTEM_TYPE" == "nd" ]]; then
                log_info "Waiting for training jobs to complete..."
                wait_for_tasks pcr_train,pinn_train,fno_train
            fi
        fi

        # Archive and send model if training succeeded.
        # In hybrid mode, NERSC-dispatched models are archived+sent by the SLURM job
        # on NERSC itself — skip the local send to avoid a redundant UCSB-side upload.
        if [[ "$SYSTEM_TYPE" == "hybrid" && "$(get_module_system "$TRAIN_MODELS")" == "nersc" ]]; then
            log_info "Hybrid NERSC job: senspot archiving handled remotely, skipping local send"
        else
            for model in $TRAIN_MODELS; do
                archive_and_send_model "$model" "$model_dir/$model" "$iteration"
            done
        fi
        stop_ram_monitor "PCR Training"
        timer_end "training"
        
        # Phase 4: Evaluate
        log_subsection "Evaluation"
        timer_start "evaluation"
        if should_skip_phase "evaluation" "$eval_dir"; then
            log_info "[SKIP] Evaluation phase - results exist at: ${eval_dir}"
        elif [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY RUN] Would run evaluation"
        else
            run_evaluation_phase "$iteration"
        fi
        timer_end "evaluation"
        
        timer_end "workflow_${WORKFLOW_NUMBER}"
        
        # Check convergence
        if check_convergence "$iteration"; then
            log_info "Convergence reached at iteration ${iteration}"
            break
        fi
    done
    
    timer_end "pipeline_total"
    
    # Print timing summary
    log_section "Pipeline Complete"
    print_timing_breakdown
    
    # Print latency summary
    if [[ -n "${LATENCY_LOG:-}" && -f "$LATENCY_LOG" ]]; then
        log_section "Queue and Wait Time Analysis"
        log_info "Latency log: ${LATENCY_LOG}"
        cat "$LATENCY_LOG" | grep -v "^$" | while read line; do
            log_info "  $line"
        done
    fi
    
    # Export metrics
    export_metrics_json "${RESULTS_DIR}/pipeline_metrics.json"

    # Auto-archive results (UCSB: storage/archived, NERSC: $SCRATCH/experiment_archive)
    if [[ "${AUTO_ARCHIVE:-false}" == "true" ]]; then
        local short_info
        short_info="iter${MAX_ITERATIONS}_$(echo "${TRAIN_MODELS}" | tr ' ' '-')"
        archive_results "$RESULTS_DIR" "$short_info"
    fi
}

run_sim_only() {
    log_section "Simulation-Only Mode"
    
    # Fetch data
    local data_dir="${RESULTS_DIR}/sim_only/data"
    if [[ "$DRY_RUN" != "true" ]]; then
        fetch_sensor_data "$data_dir"
    fi
    
    # Run single simulation batch
    run_simulation_phase "sim_only"
}

run_train_only() {
    log_section "Training-Only Mode"
    
    local sim_dir
    local sensor_dir
    
    # Use provided simulation directory or find most recent
    if [[ -n "$USE_SIMS_DIR" ]]; then
        sim_dir="$USE_SIMS_DIR"
        if [[ ! -d "$sim_dir" ]]; then
            log_error "Specified simulation directory does not exist: ${sim_dir}"
            exit 1
        fi
    else
        # Find most recent simulation results
        sim_dir=$(find "$RESULTS_DIR" -type d -name "simulations" | sort | tail -1)
        
        if [[ -z "$sim_dir" ]]; then
            log_error "No simulation results found in: ${RESULTS_DIR}"
            log_error "Run simulations first or use --use-sims <dir>"
            exit 1
        fi
    fi
    
    # Handle sensor data - required for PCR training
    if [[ -n "$USE_SENSOR_DIR" ]]; then
        sensor_dir="$USE_SENSOR_DIR"
        if [[ ! -d "$sensor_dir" ]]; then
            log_error "Specified sensor directory does not exist: ${sensor_dir}"
            exit 1
        fi
    else
        # For PCR, sensor data is mandatory
        if [[ "$TRAIN_MODELS" == *"pcr"* ]]; then
            log_error "PCR training requires sensor data. Use --use-sensor <dir>"
            log_error "Sensor directory must contain sensor_out.csv with columns: dt, windspeed, windavg"
            exit 1
        fi
        sensor_dir=""
    fi
    
    log_info "Using simulation data from: ${sim_dir}"
    [[ -n "$sensor_dir" ]] && log_info "Using sensor data from: ${sensor_dir}"
    
    # Export for training scripts
    export SENSOR_DATA_DIR="$sensor_dir"
    export SIMULATION_DATA_DIR="$sim_dir"
    
    local model_output="${RESULTS_DIR}/models"
    ensure_dir "$model_output"
    
    for model in $TRAIN_MODELS; do
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY RUN] Would train ${model} model"
        else
            run_training "$model" "$sim_dir" "${model_output}/${model}"
        fi
    done
}

################################################################################
# Execute
################################################################################

case "$MODE" in
    full)
        run_full_pipeline
        ;;
    sim-only)
        run_sim_only
        ;;
    train-only)
        run_train_only
        ;;
    *)
        log_error "Unknown mode: ${MODE}"
        log_error "Valid modes: full, sim-only, train-only"
        exit 1
        ;;
esac

log_info "Done."
echo "workflow_$WORKFLOW_NUMBER,workflow,exited,$(date '+%s.%N')" >> "$STATUS_FILE"
