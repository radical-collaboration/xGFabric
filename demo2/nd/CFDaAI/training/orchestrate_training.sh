#!/bin/bash
#
# orchestrate_training.sh - Training orchestration for all model types
#
# Handles PCR (CPU distributed), PINN (GPU), and FNO (GPU) training
# with automatic dispatch to appropriate execution mode.
#
# Usage:
#   source training/orchestrate_training.sh
#   run_training <model_type> <data_dir> <output_dir>

################################################################################
# Model Archiving and Sending via CSPOT
################################################################################

# Check if senspot-file-send is available
check_senspot_file_send() {
    if command -v senspot-file-send &>/dev/null; then
        return 0
    fi
    
    # If senspot-get is available, senspot-file-send should be in the same directory
    if command -v senspot-get &>/dev/null; then
        local senspot_dir=$(dirname "$(command -v senspot-get)")
        if [[ -x "${senspot_dir}/senspot-file-send" ]]; then
            return 0
        fi
    fi
    
    # Check standard paths (matching system_config.sh detection logic)
    local paths=(
        "$HOME/bin/senspot-file-send"
        "$HOME/common/cspot/build/bin/senspot-file-send"
        "/global/common/software/m5290/cspot/build/bin/senspot-file-send"
    )
    
    for path in "${paths[@]}"; do
        if [[ -x "$path" ]]; then
            # Add to PATH temporarily
            export PATH="$(dirname "$path"):$PATH"
            return 0
        fi
    done
    
    return 1
}

# Archive and send model files after training
# Args: model_type output_dir iteration
archive_and_send_model() {
    local model_type="$1"
    local output_dir="$2"
    local iteration="${3:-unknown}"
    
    # Skip if SENSPOT_SEND_MODELS is explicitly disabled
    if [[ "${SENSPOT_SEND_MODELS:-true}" != "true" ]]; then
        log_info "Model sending disabled (SENSPOT_SEND_MODELS=false)"
        return 0
    fi
    
    # Check if senspot-file-send is available
    if ! check_senspot_file_send; then
        log_warn "senspot-file-send not found - skipping model upload"
        log_warn "Install CSPOT tools or set SENSPOT_SEND_MODELS=false to disable"
        return 0
    fi
    
    log_subsection "Archiving and sending ${model_type} model"
    
    # Create archive directory
    local archive_dir="${output_dir}/archives"
    ensure_dir "$archive_dir"
    
    # Generate archive filename with timestamp and iteration
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local archive_name="${model_type}_iter${iteration}_${timestamp}.tar.gz"
    local archive_path="${archive_dir}/${archive_name}"
    
    # Determine which files to archive based on model type
    local files_to_archive=()

    if [[ "${SYSTEM_TYPE}" == "nd" ]]; then
        HERE=`pwd`
        output_dir="$HERE/$output_dir"
        archive_path="$HERE/$archive_path"
    fi
    
    case "$model_type" in
        pcr)
            # PCR: CSV coefficient files and summary JSON
            mapfile -t files_to_archive < <(find "$output_dir" -type f \( -name 'pcr_coefficients_*.csv' -o -name 'training_summary.json' \) 2>/dev/null)
            ;;
        pinn)
            # PINN: h5 weights and JSON metadata files (check subdirectories for experiment_* dirs)
            mapfile -t files_to_archive < <(find "$output_dir" -type f \( -name '*.weights.h5' -o -name '*.normalization.json' -o -name '*.model_meta.json' -o -name '*.run.json' \) 2>/dev/null)
            ;;
        fno)
            # FNO: h5 weights and JSON metadata files
            mapfile -t files_to_archive < <(find "$output_dir" -type f \( -name 'model.weights.h5' -o -name 'model_meta.json' -o -name 'test_metrics.json' -o -name 'normalization.json' \) 2>/dev/null)
            ;;
        *)
            log_error "Unknown model type for archiving: ${model_type}"
            return 1
            ;;
    esac
    
    # Check if we found any files
    if [[ ${#files_to_archive[@]} -eq 0 ]]; then
        log_warn "No model files found to archive in: ${output_dir}"
        return 0
    fi
    
    log_info "Found ${#files_to_archive[@]} files to archive"
    
    # Create tar archive (use relative paths within output_dir)
    pushd "$output_dir" > /dev/null
    local relative_files=()
    for file in "${files_to_archive[@]}"; do
        # Use path relative to output_dir, not just basename
        local rel_path="${file#$output_dir/}"
        relative_files+=("$rel_path")
    done
    
    if tar -czf "$archive_path" "${relative_files[@]}"; then
        local archive_size=$(du -h "$archive_path" | cut -f1)
        log_info "✓ Created archive: ${archive_name} (${archive_size})"
    else
        log_error "✗ Failed to create archive: ${archive_path}"
        popd > /dev/null
        return 1
    fi
    popd > /dev/null
    
    # Send via senspot-file-send
    local woof_endpoint="${SENSPOT_MODELS_ENDPOINT:-woof://169.231.230.76/sharedfs/models}/${model_type}.sb.woof"
    local send_log="${archive_dir}/send_${model_type}_${timestamp}.log"
    
    log_info "Sending to: ${woof_endpoint}"
    
    # Send with verbose output redirected to log only (not console)
    if senspot-file-send -f "$archive_path" -W "$woof_endpoint" -V > "$send_log" 2>&1; then
        # Extract transfer rate from log for summary
        local transfer_rate=$(grep -oP '\d+\.\d+ megabytes / second' "$send_log" | head -1 || echo "")
        if [[ -n "$transfer_rate" ]]; then
            log_info "✓ Model successfully sent to CSPOT ($transfer_rate)"
        else
            log_info "✓ Model successfully sent to CSPOT"
        fi
        
        # Optionally remove local archive after successful send
        if [[ "${SENSPOT_KEEP_ARCHIVES:-true}" != "true" ]]; then
            rm -f "$archive_path"
            log_info "Local archive removed (SENSPOT_KEEP_ARCHIVES=false)"
        fi
    else
        log_error "✗ Failed to send model to CSPOT"
        log_error "Check details in: ${send_log}"
        log_error "Archive preserved at: ${archive_path}"
        return 1
    fi
}

################################################################################
# Training Dispatch
################################################################################

run_training() {
    local model_type="$1"
    local data_dir="$2"
    local output_dir="$3"
    local extra_args="${4:-}"
    
    require_dir "$data_dir" "Training data directory"
    ensure_dir "$output_dir"
    
    timer_start "training_${model_type}"
    log_section "Training: ${model_type^^}"
    
    local training_result=0
    case "$model_type" in
        pcr)
            _run_pcr_training "$data_dir" "$output_dir" "$extra_args"
            training_result=$?
            ;;
        pinn)
            _run_pinn_training "$data_dir" "$output_dir" "$extra_args"
            training_result=$?
            ;;
        fno)
            _run_fno_training "$data_dir" "$output_dir" "$extra_args"
            training_result=$?
            ;;
        *)
            log_error "Unknown model type: ${model_type}"
            log_error "Supported types: pcr, pinn, fno"
            return 1
            ;;
    esac
    
    timer_end "training_${model_type}"
    
    return $training_result
}

################################################################################
# PCR Training (Distributed CPU)
################################################################################

_run_pcr_training() {
    local data_dir="$1"
    local output_dir="$2"
    local extra_args="$3"
    
    log_info "Preparing PCR training..."
    
    # PCR uses grid-based distributed training
    local grid_config="${WORK_DIR}/grid_config.json"
    
    require_file "$grid_config" "Grid configuration"
    
    case "$SYSTEM_TYPE" in
        nersc)
            _run_pcr_slurm "$data_dir" "$output_dir" "$grid_config"
            ;;
        nd)
            _run_pcr_uge "$data_dir" "$output_dir" "$grid_config"
            ;;
        ucsb|*)
            if [[ "${HAS_MACHINE_LIST:-false}" == "true" ]]; then
                _run_pcr_distributed "$data_dir" "$output_dir" "$grid_config"
            else
                _run_pcr_local "$data_dir" "$output_dir" "$grid_config"
            fi
            ;;
    esac
}

_run_pcr_slurm() {
    local data_dir="$1"     # simulation data directory
    local output_dir="$2"
    local grid_config="$3"
    
    log_info "Submitting PCR training to SLURM..."
    
    # Get sensor data directory from environment (set by main.sh)
    local sensor_dir="${SENSOR_DATA_DIR:-}"
    if [[ -z "$sensor_dir" || ! -d "$sensor_dir" ]]; then
        log_error "SENSOR_DATA_DIR not set or directory not found"
        log_error "PCR training requires sensor data. Use --use-sensor <dir>"
        return 1
    fi
    
    # Verify sensor_out.csv exists
    if [[ ! -f "${sensor_dir}/sensor_out.csv" ]]; then
        log_error "sensor_out.csv not found in ${sensor_dir}"
        log_error "Expected CSV with columns: dt, windspeed, windavg"
        return 1
    fi
    
    log_info "Sensor data: ${sensor_dir}"
    log_info "Simulation data: ${data_dir}"
    log_info "Grid config: ${grid_config}"
    
    local partitions_dir="${output_dir}/partitions"
    ensure_dir "$partitions_dir"
    
    # Step 1: Generate partitions from grid config
    # Default to 1 partition for single-node training
    local num_partitions="${PCR_NUM_PARTITIONS:-1}"
    local partition_script="${WORK_DIR}/training/pcr/partition_pcr_grid.py"
    local partitions_file="${partitions_dir}/pcr_partitions_full.json"
    
    if [[ -f "$partition_script" ]]; then
        log_info "Partitioning grid into ${num_partitions} partitions..."
        export GRID_CONFIG_PATH="$grid_config"
        pushd "$partitions_dir" > /dev/null
        python3 "$partition_script" "$num_partitions"
        popd > /dev/null
        
        if [[ ! -f "$partitions_file" ]]; then
            log_error "✗ Partitioning failed - ${partitions_file} not created"
            return 1
        fi
        log_info "✓ Grid partitioned into ${num_partitions} partitions"
    else
        log_error "✗ Partition script not found: ${partition_script}"
        return 1
    fi
    
    # Step 2: Prepare data for all partitions
    local prep_script="${WORK_DIR}/training/pcr/prepare_pcr_data.py"
    
    if [[ -f "$prep_script" ]]; then
        log_info "Preparing PCR data partitions..."
        # Args: sensor_folder simulations_folder partitions_file output_dir
        python3 "$prep_script" "$sensor_dir" "$data_dir" "$partitions_file" "$partitions_dir"
    else
        log_error "Data preparation script not found: ${prep_script}"
        return 1
    fi
    
    # Step 3: Submit array job
    local slurm_script="${WORK_DIR}/slurm/pcr_train_slurm.sh"
    
    local job_id=$(sbatch \
        --array="0-$((num_partitions-1))" \
        --output="${SLURM_LOGS_DIR}/pcr_%A_%a.out" \
        --error="${SLURM_LOGS_DIR}/pcr_%A_%a.err" \
        "$slurm_script" "$data_dir" "$output_dir" "$partitions_file" \
        | awk '{print $4}')
    
    log_info "Submitted PCR job array: ${job_id}"
    echo "$job_id"
}

_run_pcr_uge() {
    local data_dir="$1"     # simulation data directory
    local output_dir="$2"
    local grid_config="$3"
    
    log_info "Submitting PCR training to UGE..."
    
    # Get sensor data directory from environment (set by main.sh)
    local sensor_dir="${SENSOR_DATA_DIR:-}"
    if [[ -z "$sensor_dir" || ! -d "$sensor_dir" ]]; then
        log_error "SENSOR_DATA_DIR not set or directory not found"
        log_error "PCR training requires sensor data. Use --use-sensor <dir>"
        return 1
    fi
    
    # Verify sensor_out.csv exists
    if [[ ! -f "${sensor_dir}/sensor_out.csv" ]]; then
        log_error "sensor_out.csv not found in ${sensor_dir}"
        log_error "Expected CSV with columns: dt, windspeed, windavg"
        return 1
    fi
    
    log_info "Sensor data: ${sensor_dir}"
    log_info "Simulation data: ${data_dir}"
    log_info "Grid config: ${grid_config}"
    
    local partitions_dir="${output_dir}/partitions"
    ensure_dir "$partitions_dir"
    
    # Step 1: Generate partitions from grid config
    # Default to 1 partition for single-node training
    local num_partitions="${PCR_NUM_PARTITIONS:-1}"
    local partition_script="${WORK_DIR}/training/pcr/partition_pcr_grid.py"
    local partitions_file="${partitions_dir}/pcr_partitions_full.json"
    
    if [[ -f "$partition_script" ]]; then
        log_info "Partitioning grid into ${num_partitions} partitions..."
        export GRID_CONFIG_PATH="$grid_config"
        pushd "$partitions_dir" > /dev/null
        python3 "$partition_script" "$num_partitions"
        popd > /dev/null
        
        if [[ ! -f "$partitions_file" ]]; then
            log_error "✗ Partitioning failed - ${partitions_file} not created"
            return 1
        fi
        log_info "✓ Grid partitioned into ${num_partitions} partitions"
    else
        log_error "✗ Partition script not found: ${partition_script}"
        return 1
    fi
    
    # Step 2: Prepare data for all partitions
    local prep_script="${WORK_DIR}/training/pcr/prepare_pcr_data.py"
    
    if [[ -f "$prep_script" ]]; then
        log_info "Preparing PCR data partitions..."
        # Args: sensor_folder simulations_folder partitions_file output_dir
        python3 "$prep_script" "$sensor_dir" "$data_dir" "$partitions_file" "$partitions_dir"
    else
        log_error "Data preparation script not found: ${prep_script}"
        return 1
    fi
    
    # Step 3: Submit array job
    local uge_script="${WORK_DIR}/uge/pcr_train_uge.sh"
    
    job_id=$(qsub \
        -terse \
        -pe smp $SIMULATION_THREADS \
        -q long \
        -t "1-$num_partitions" \
        -o "logs/$COORD_RUN_NAME/workflows/$WORKFLOW_NUMBER/training/\$JOB_NAME_\$JOB_ID.out" \
        -e "logs/$COORD_RUN_NAME/workflows/$WORKFLOW_NUMBER/training/\$JOB_NAME_\$JOB_ID.err" \
        "$uge_script" "$partitions_dir" "$output_dir"
    )

    log_info "Submitted PCR job array: ${job_id}"
    echo "workflow_$WORKFLOW_NUMBER,pcr_train,submitted,$(date '+%s.%N')" >> "$STATUS_FILE"
    JOB_IDS["pcr_train"]="$job_id"
}

_run_pcr_distributed() {
    local data_dir="$1"
    local output_dir="$2"
    local grid_config="$3"
    
    log_info "Running distributed PCR training via SSH..."
    
    # Get sensor data directory (required for PCR)
    local sensor_dir="${SENSOR_DATA_DIR:-}"
    if [[ -z "$sensor_dir" || ! -d "$sensor_dir" ]]; then
        log_error "SENSOR_DATA_DIR not set or directory not found"
        return 1
    fi
    
    # Use the train_pcr_chunk.py for distributed training
    local train_script="${WORK_DIR}/training/pcr/train_pcr_chunk.py"
    local partition_script="${WORK_DIR}/training/pcr/partition_pcr_grid.py"
    
    if [[ ! -f "$train_script" ]]; then
        log_error "PCR training script not found"
        return 1
    fi
    
    # Get list of machines (read both hostname and IP)
    # Format: hostname IP or just IP
    local machine_names=()
    local machine_ips=()
    while read -r name ip; do
        machine_names+=("$name")
        # If second field exists, use it as IP; otherwise use first field
        machine_ips+=("${ip:-$name}")
    done < "${WORK_DIR}/machine_list.txt"
    local num_machines=${#machine_ips[@]}

    # Cap PCR machines to avoid over-partitioning
    local pcr_max="${PCR_MAX_MACHINES:-20}"
    if [[ $num_machines -gt $pcr_max ]]; then
        log_info "Capping PCR machines from ${num_machines} to ${pcr_max}"
        machine_names=("${machine_names[@]:0:$pcr_max}")
        machine_ips=("${machine_ips[@]:0:$pcr_max}")
        num_machines=$pcr_max
    fi

    # Create partitions directory
    local partitions_dir="${output_dir}/partitions"
    ensure_dir "$partitions_dir"
    
    # Step 1: Generate partitions from grid config
    local partitions_file="${partitions_dir}/pcr_partitions_full.json"
    
    if [[ -f "$partition_script" ]]; then
        log_info "Partitioning grid into ${num_machines} partitions..."
        export GRID_CONFIG_PATH="$grid_config"
        pushd "$partitions_dir" > /dev/null
        python3 "$partition_script" "$num_machines"
        popd > /dev/null
        
        if [[ ! -f "$partitions_file" ]]; then
            log_error "Partitioning failed - ${partitions_file} not created"
            return 1
        fi
    else
        log_error "Partition script not found: ${partition_script}"
        return 1
    fi
    
    # Step 2: Prepare data for all partitions
    local prep_script="${WORK_DIR}/training/pcr/prepare_pcr_data.py"
    
    if [[ -f "$prep_script" ]]; then
        log_info "Preparing PCR data partitions..."
        python3 "$prep_script" "$sensor_dir" "$data_dir" "$partitions_file" "$partitions_dir"
    else
        log_error "Data preparation script not found: ${prep_script}"
        return 1
    fi
    
    # Get partition IDs from generated file
    local partitions
    mapfile -t partitions < <(python3 "${WORK_DIR}/utils/read_partitions.py" "$partitions_file")
    local num_partitions=${#partitions[@]}
    
    log_info "Distributing ${num_partitions} partitions across ${num_machines} machines"
    
    # Create local output directories for results
    for i in "${!partitions[@]}"; do
        local partition_id="${partitions[$i]}"
        mkdir -p "${output_dir}/partition_${partition_id}"
    done
    
    # Distribute work across machines
    local pids=()
    for i in "${!partitions[@]}"; do
        local partition_id="${partitions[$i]}"
        local machine_idx=$((i % num_machines))
        local machine_name="${machine_names[$machine_idx]}"
        local machine_ip="${machine_ips[$machine_idx]}"
        
        log_info "  Partition ${partition_id} -> ${machine_name} ${machine_ip}"
        
        # Setup paths (unique per partition to avoid conflicts)
        local remote_work_dir="/tmp/pcr_training_$$_${partition_id}"
        local data_file="${partitions_dir}/machine_${partition_id}_data.pkl"
        local remote_data_file="${remote_work_dir}/data.pkl"
        local remote_script="${remote_work_dir}/train.py"
        local remote_output_dir="${remote_work_dir}/output"
        local local_output_dir="${output_dir}/partition_${partition_id}"
        
        # Deploy and run on remote machine in background (use IP for SSH connection)
        (
            # Create remote directory and copy files
            ssh -i "${WORK_DIR}/id_rsa" "$machine_ip" "mkdir -p ${remote_work_dir}" 2>/dev/null
            scp -i "${WORK_DIR}/id_rsa" -q "$data_file" "${machine_ip}:${remote_data_file}" 2>/dev/null
            scp -i "${WORK_DIR}/id_rsa" -q "$train_script" "${machine_ip}:${remote_script}" 2>/dev/null
            
            # Run training remotely with conda environment activated
            ssh -i "${WORK_DIR}/id_rsa" "$machine_ip" "
                source ~/miniforge3/etc/profile.d/conda.sh 2>/dev/null || source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null
                conda activate cfdai_intheloop
                cd ${remote_work_dir}
                python3 train.py ${remote_data_file} ${remote_output_dir}
            " 2>&1 | sed "s/^/[${machine_name}] /"
            
            # Copy results back
            scp -i "${WORK_DIR}/id_rsa" -q -r "${machine_ip}:${remote_output_dir}/*" "${local_output_dir}/" 2>/dev/null
            
            # Cleanup remote files
            ssh -i "${WORK_DIR}/id_rsa" "$machine_ip" "rm -rf ${remote_work_dir}" 2>/dev/null
        ) &
        
        pids+=($!)
    done
    
    # Wait for all
    local failed=0
    local completed=0
    for pid in "${pids[@]}"; do
        if wait "$pid"; then
            completed=$((completed + 1))
            log_debug "✓ Training job $pid completed"
        else
            failed=$((failed + 1))
            log_warn "✗ Training job $pid failed"
        fi
    done
    
    log_info "PCR training: ${completed} succeeded, ${failed} failed"
    if [[ $failed -gt 0 ]]; then
        log_warn "PCR training: ${failed} partitions failed"
    fi
    
    # Merge results
    _merge_pcr_results "$output_dir"
}

_run_pcr_local() {
    local data_dir="$1"
    local output_dir="$2"
    local grid_config="$3"
    
    log_info "Running PCR training locally (sequential)..."
    
    # Get sensor data directory (required for PCR)
    local sensor_dir="${SENSOR_DATA_DIR:-}"
    if [[ -z "$sensor_dir" || ! -d "$sensor_dir" ]]; then
        log_error "SENSOR_DATA_DIR not set or directory not found"
        return 1
    fi
    
    local train_script="${WORK_DIR}/training/pcr/train_pcr_chunk.py"
    local partition_script="${WORK_DIR}/training/pcr/partition_pcr_grid.py"
    
    # Create partitions directory
    local partitions_dir="${output_dir}/partitions"
    ensure_dir "$partitions_dir"
    
    # Step 1: Generate single partition (all points)
    local num_partitions=1
    local partitions_file="${partitions_dir}/pcr_partitions_full.json"
    
    if [[ -f "$partition_script" ]]; then
        log_info "Generating grid partition..."
        export GRID_CONFIG_PATH="$grid_config"
        pushd "$partitions_dir" > /dev/null
        python3 "$partition_script" "$num_partitions"
        popd > /dev/null
        
        if [[ ! -f "$partitions_file" ]]; then
            log_error "Partitioning failed - ${partitions_file} not created"
            return 1
        fi
    else
        log_error "Partition script not found: ${partition_script}"
        return 1
    fi
    
    # Step 2: Prepare data
    local prep_script="${WORK_DIR}/training/pcr/prepare_pcr_data.py"
    
    if [[ -f "$prep_script" ]]; then
        log_info "Preparing PCR data..."
        python3 "$prep_script" "$sensor_dir" "$data_dir" "$partitions_file" "$partitions_dir"
    else
        log_error "Data preparation script not found: ${prep_script}"
        return 1
    fi
    
    # Step 3: Train sequentially
    for partition_id in 0; do
        log_info "Training partition ${partition_id}..."
        
        python3 "$train_script" \
            --sensor "$sensor_dir" \
            --data "$data_dir" \
            --partition "$partition_id" \
            --grid-config "$partitions_file" \
            --output "${output_dir}/partition_${partition_id}"
    done
    
    _merge_pcr_results "$output_dir"
}

_merge_pcr_results() {
    local output_dir="$1"
    
    log_info "Merging PCR partition results..."
    
    # Combine all partition outputs
    # (Implementation depends on PCR output format)
    find "$output_dir" -name "partition_*" -type d | while read -r part_dir; do
        # Copy results to main output
        cp "${part_dir}"/*.bin "${output_dir}/" 2>/dev/null || true
    done
}

################################################################################
# PINN Training (GPU)
################################################################################

_run_pinn_training() {
    local data_dir="$1"
    local output_dir="$2"
    local extra_args="$3"
    
    log_info "Preparing PINN training..."
    
    if [[ "$HAS_GPU" != "true" ]]; then
        log_warn "No GPU detected - PINN training may be slow"
    fi
    
    local pinn_script="${WORK_DIR}/training/pinn/train_pinn.py"
    
    case "$SYSTEM_TYPE" in
        nersc)
            _run_pinn_slurm "$data_dir" "$output_dir" "$pinn_script" "$extra_args"
            ;;
        nd)
            _run_pinn_uge "$data_dir" "$output_dir" "$pinn_script" "$extra_args"
            ;;
        hybrid)
            if [[ "$(get_module_system pinn)" == "nersc" ]]; then
                _run_pinn_nersc_via_ssh "$data_dir" "$output_dir" "$extra_args"
            else
                _run_pinn_local "$data_dir" "$output_dir" "$pinn_script" "$extra_args"
            fi
            ;;
        *)
            _run_pinn_local "$data_dir" "$output_dir" "$pinn_script" "$extra_args"
            ;;
    esac
}

_run_pinn_slurm() {
    local data_dir="$1"
    local output_dir="$2"
    local script="$3"
    local extra_args="$4"
    
    local slurm_script="${WORK_DIR}/slurm/pinn_train_slurm.sh"
    
    local job_id=$(sbatch \
        --output="${SLURM_LOGS_DIR}/pinn_%j.out" \
        --error="${SLURM_LOGS_DIR}/pinn_%j.err" \
        "$slurm_script" "$data_dir" "$output_dir" "$script" "$extra_args" \
        | awk '{print $4}')
    
    log_info "Submitted PINN training job: ${job_id}"
    echo "$job_id"
}

_run_pinn_uge() {
    local data_dir="$1"
    local output_dir="$2"
    local script="$3"
    local extra_args="$4"
    
    local uge_script="${WORK_DIR}/uge/pinn_train_uge.sh"
    
    job_id=$(qsub \
        -pe smp $SIMULATION_THREADS \
        -q gpu \
        -l gpu_card=1 \
        -o "logs/$COORD_RUN_NAME/workflows/$WORKFLOW_NUMBER/training/\$JOB_NAME_\$JOB_ID.out" \
        -e "logs/$COORD_RUN_NAME/workflows/$WORKFLOW_NUMBER/training/\$JOB_NAME_\$JOB_ID.err" \
        "$uge_script" "$data_dir" "$output_dir" "$script" "$extra_args" \
        | awk '{print $3}'
    )

    log_info "Submitted PINN training job: ${job_id}"
    echo "workflow_$WORKFLOW_NUMBER,pinn_train,submitted,$(date '+%s.%N')" >> "$STATUS_FILE"
    JOB_IDS["pinn_train"]="$job_id"
}

_run_pinn_local() {
    local data_dir="$1"
    local output_dir="$2"
    local script="$3"
    local extra_args="$4"
    
    if [[ -f "$script" ]]; then
        mkdir -p "$output_dir"
        # train_pinn.py expects: <csv_dir> <model_name> [options]
        python3 "$script" \
            "$data_dir" \
            "pinn_model" \
            --output_dir "$output_dir" \
            $extra_args
    else
        log_error "PINN training script not found: ${script}"
        return 1
    fi
}

################################################################################
# FNO Training (GPU)
################################################################################

_run_fno_training() {
    local data_dir="$1"
    local output_dir="$2"
    local extra_args="$3"
    
    log_info "Preparing FNO training..."
    
    if [[ "$HAS_GPU" != "true" ]]; then
        log_warn "No GPU detected - FNO training will be slow on CPU"
    fi
    
    local fno_script="${WORK_DIR}/training/fno/train_fno.py"
    
    case "$SYSTEM_TYPE" in
        nersc)
            _run_fno_slurm "$data_dir" "$output_dir" "$fno_script" "$extra_args"
            ;;
        nd)
            _run_fno_uge "$data_dir" "$output_dir" "$fno_script" "$extra_args"
            ;;
        hybrid)
            if [[ "$(get_module_system fno)" == "nersc" ]]; then
                _run_fno_nersc_via_ssh "$data_dir" "$output_dir" "$extra_args"
            else
                _run_fno_local "$data_dir" "$output_dir" "$fno_script" "$extra_args"
            fi
            ;;
        *)
            _run_fno_local "$data_dir" "$output_dir" "$fno_script" "$extra_args"
            ;;
    esac
}

_run_fno_slurm() {
    local data_dir="$1"
    local output_dir="$2"
    local script="$3"
    local extra_args="$4"
    
    local slurm_script="${WORK_DIR}/slurm/fno_train_slurm.sh"
    
    mkdir -p "$output_dir"
    
    local job_id=$(sbatch \
        --output="${SLURM_LOGS_DIR}/fno_%j.out" \
        --error="${SLURM_LOGS_DIR}/fno_%j.err" \
        "$slurm_script" "$data_dir" "$output_dir" "$script" "$extra_args" \
        | awk '{print $4}')
    
    log_info "Submitted FNO training job: ${job_id}"
    echo "$job_id"
}

_run_fno_uge() {
    local data_dir="$1"
    local output_dir="$2"
    local script="$3"
    local extra_args="$4"
    
    local uge_script="${WORK_DIR}/uge/fno_train_uge.sh"
    
    mkdir -p "$output_dir"
    
    job_id=$(qsub \
        -pe smp $SIMULATION_THREADS \
        -q gpu \
        -l gpu_card=1 \
        -o "logs/$COORD_RUN_NAME/workflows/$WORKFLOW_NUMBER/training/\$JOB_NAME_\$JOB_ID.out" \
        -e "logs/$COORD_RUN_NAME/workflows/$WORKFLOW_NUMBER/training/\$JOB_NAME_\$JOB_ID.err" \
        "$uge_script" "$data_dir" "$output_dir" "$script" "$extra_args" \
        | awk '{print $3}'
    )

    log_info "Submitted FNO training job: ${job_id}"
    echo "workflow_$WORKFLOW_NUMBER,fno_train,submitted,$(date '+%s.%N')" >> "$STATUS_FILE"
    JOB_IDS["fno_train"]="$job_id"
}

_run_fno_local() {
    local data_dir="$1"
    local output_dir="$2"
    local script="$3"
    local extra_args="$4"
    
    if [[ -f "$script" ]]; then
        mkdir -p "$output_dir"
        # train_fno.py expects: --data-dir <dir> --output-dir <dir>
        python3 "$script" \
            --data-dir "$data_dir" \
            --output-dir "$output_dir" \
            $extra_args
    else
        log_error "FNO training script not found: ${script}"
        return 1
    fi
}

################################################################################
# Hybrid Mode — NERSC Dispatch via SSH
################################################################################

# _record_hybrid_job_id <model> <job_id> <remote_output_dir>
# Appends job metadata to a state file so IDs survive a UCSB process crash.
_record_hybrid_job_id() {
    local model="$1"
    local job_id="$2"
    local remote_output="$3"
    local jobs_file="${RESULTS_DIR:-${WORK_DIR}/results}/hybrid_jobs.txt"
    printf "%s  model=%-6s  job_id=%-12s  remote_output=%s\n" \
        "$(date -Iseconds)" "$model" "$job_id" "$remote_output" >> "$jobs_file"
    log_info "Job ID recorded → ${jobs_file}"
}

# _sync_scripts_to_nersc
# Rsyncs slurm/ scripts from local WORK_DIR to NERSC_REMOTE_WORK_DIR.
# Called once before first job submission so sbatch can find the scripts.
_sync_scripts_to_nersc() {
    local ssh_key="${NERSC_SSH_KEY:-${WORK_DIR}/nersc}"
    local user="${NERSC_USER:-kurl}"
    local host="${NERSC_SSH_HOST:-perlmutter.nersc.gov}"
    local remote_work="${NERSC_REMOTE_WORK_DIR:-/global/homes/k/kurl/intheloop}"

    log_info "  [sync →] slurm scripts → ${user}@${host}:${remote_work}/slurm/"

    ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" "mkdir -p '${remote_work}/slurm'" || {
        log_error "Failed to create remote slurm dir: ${remote_work}/slurm"
        return 1
    }

    local rsync_out rsync_rc=0
    rsync_out=$(rsync -az --no-perms \
        -e "ssh -i '${ssh_key}' -q -o BatchMode=yes -o StrictHostKeyChecking=no" \
        "${WORK_DIR}/slurm/" "${user}@${host}:${remote_work}/slurm/" 2>&1) || rsync_rc=$?
    if [[ $rsync_rc -ne 0 ]]; then
        log_error "Failed to sync slurm scripts to NERSC (exit ${rsync_rc}):"
        log_error "${rsync_out}"
        return 1
    fi
    log_info "  [sync ✓] slurm scripts synced to NERSC"
}

# _sync_data_to_nersc <local_dir> <remote_label>
# Rsyncs a local directory to NERSC scratch.
# Echoes the remote absolute path on success.
_sync_data_to_nersc() {
    local local_dir="$1"
    local remote_label="${2:-data}"

    local ssh_key="${NERSC_SSH_KEY:-${WORK_DIR}/id_rsa}"
    local user="${NERSC_USER:-kurl}"
    local host="${NERSC_SSH_HOST:-perlmutter.nersc.gov}"
    local remote_base="${NERSC_SCRATCH_DIR:-/pscratch/sd/k/kurl}/intheloop_hybrid"
    local remote_dir="${remote_base}/${remote_label}"

    log_info "  [sync →] ${local_dir}"
    log_info "  [sync →] ${user}@${host}:${remote_dir}"

    ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" "mkdir -p '${remote_dir}'" || {
        log_error "Failed to create remote directory: ${remote_dir}"
        return 1
    }

    local rsync_out rsync_rc=0
    rsync_out=$(rsync -az --no-perms --stats \
        -e "ssh -i '${ssh_key}' -q -o BatchMode=yes -o StrictHostKeyChecking=no" \
        "${local_dir}/" "${user}@${host}:${remote_dir}/" 2>&1) || rsync_rc=$?
    # Exit code 23 = "some files not transferred". When 0 bytes were transferred,
    # it may mean all files already exist on the remote — verify by checking remote file count.
    if [[ $rsync_rc -eq 23 ]]; then
        local transferred
        transferred=$(echo "$rsync_out" | grep -oP 'Total transferred file size: \K[\d,]+')
        if [[ "${transferred//,/}" == "0" ]]; then
            local remote_count
            remote_count=$(ssh -q -i "$ssh_key" -o BatchMode=yes -o StrictHostKeyChecking=no \
                "${user}@${host}" "ls '${remote_dir}' 2>/dev/null | wc -l" 2>/dev/null || echo 0)
            if [[ $remote_count -gt 0 ]]; then
                log_info "  [sync] ${remote_count} files already present on NERSC — skipping transfer"
                rsync_rc=0
            else
                log_error "rsync transferred 0 bytes and remote dir is empty: ${remote_dir}"
                log_error "Source may be empty or inaccessible: ${local_dir}"
                log_error "${rsync_out}"
                return 1
            fi
        fi
    fi
    if [[ $rsync_rc -ne 0 ]]; then
        log_error "rsync failed (exit ${rsync_rc}): ${local_dir} -> ${remote_dir}"
        log_error "${rsync_out}"
        return 1
    fi
    echo "$rsync_out" | grep -E '^(Number of files|Total file size|Total transferred|sent |bytes/sec)' \
        | while IFS= read -r line; do log_info "  [rsync] ${line}"; done

    log_info "  [sync ✓] Data available at: ${remote_dir}"
    echo "$remote_dir"
}

# _wait_nersc_slurm_job <job_id>
# Polls via SSH until the SLURM job leaves the queue, then checks sacct state.
# Returns 0 on COMPLETED, 1 otherwise.
_wait_nersc_slurm_job() {
    local job_id="$1"
    local ssh_key="${NERSC_SSH_KEY:-${WORK_DIR}/id_rsa}"
    local user="${NERSC_USER:-kurl}"
    local host="${NERSC_SSH_HOST:-perlmutter.nersc.gov}"
    local poll_start=$(date +%s)

    log_info "  [wait] Polling NERSC job ${job_id} every 60s..."

    while true; do
        local squeue_rc=0
        ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
            "${user}@${host}" "squeue -j ${job_id} &>/dev/null 2>&1" || squeue_rc=$?
        if [[ $squeue_rc -ne 0 ]]; then
            # squeue returned non-zero — could be job gone OR transient SSH/scheduler error.
            # Double-check: query squeue with output to see if job is truly absent.
            local squeue_state
            squeue_state=$(ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
                "${user}@${host}" \
                "squeue -j ${job_id} --format='%T' --noheader 2>/dev/null | head -1 | xargs" \
                2>/dev/null || true)
            if [[ -z "$squeue_state" ]]; then
                # Job truly gone from squeue — proceed to sacct check
                break
            fi
            # Job is still in squeue (PENDING/RUNNING) — transient error, keep waiting
            local elapsed=$(( $(date +%s) - poll_start ))
            log_info "  [wait] Job ${job_id} ${squeue_state}... $(( elapsed / 60 ))m elapsed (squeue transient error, retrying)"
            sleep 60
        else
            local elapsed=$(( $(date +%s) - poll_start ))
            log_info "  [wait] Job ${job_id} running... $(( elapsed / 60 ))m elapsed"
            sleep 60
        fi
    done

    local total_wait=$(( $(date +%s) - poll_start ))

    local state
    state=$(ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" \
        "sacct -j ${job_id} --format=State --noheader 2>/dev/null | head -1 | xargs" \
        2>/dev/null || echo "UNKNOWN")

    if [[ "$state" == "COMPLETED" ]]; then
        log_info "  [wait ✓] Job ${job_id} COMPLETED (waited $(format_duration $total_wait))"
        return 0
    else
        log_error "  [wait ✗] Job ${job_id} ended with state: ${state} (waited $(format_duration $total_wait))"
        # Fetch sacct details and tail the job log so the error is visible locally
        log_error "  [sacct] Job details:"
        ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
            "${user}@${host}" \
            "sacct -j ${job_id} --format=JobID,JobName,State,ExitCode,Elapsed,NodeList --noheader 2>/dev/null" \
            2>/dev/null | while IFS= read -r line; do log_error "    ${line}"; done
        local log_path
        log_path=$(ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
            "${user}@${host}" \
            "ls -t ${NERSC_LOGS_DIR:-/global/homes/k/kurl/jobs_logs}/hybrid_*_${job_id}.out \
                   ${NERSC_LOGS_DIR:-/global/homes/k/kurl/jobs_logs}/*_${job_id}.out 2>/dev/null | head -1" \
            2>/dev/null || true)
        if [[ -n "$log_path" ]]; then
            log_error "  [log tail] ${log_path} (last 40 lines):"
            ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
                "${user}@${host}" "tail -40 '${log_path}' 2>/dev/null" \
                2>/dev/null | while IFS= read -r line; do log_error "    ${line}"; done
        else
            log_error "  [log tail] No job log found for job ${job_id}"
        fi
        return 1
    fi
}

################################################################################
# Hybrid NERSC primitives: submit, collect, batch orchestration
################################################################################

# _nersc_prepare_and_submit <model> <data_dir> <local_output_dir> [remote_data_dir]
# Submits a SLURM job on NERSC.
# If remote_data_dir is provided, skips the rsync (data already on NERSC).
# Prints "job_id:remote_output_dir" to stdout on success.
_nersc_prepare_and_submit() {
    local model="$1"
    local data_dir="$2"
    local local_output_dir="$3"
    local remote_data_dir="${4:-}"   # optional pre-synced path

    local ssh_key="${NERSC_SSH_KEY:-${WORK_DIR}/nersc}"
    local user="${NERSC_USER:-kurl}"
    local host="${NERSC_SSH_HOST:-perlmutter.nersc.gov}"
    local remote_work="${NERSC_REMOTE_WORK_DIR:-/global/homes/k/kurl/intheloop}"
    local logs_dir="${NERSC_LOGS_DIR:-/global/homes/k/kurl/jobs_logs}"
    local remote_base="${NERSC_SCRATCH_DIR:-/pscratch/sd/k/kurl}/intheloop_hybrid"

    local iter_tag
    iter_tag=$(echo "$data_dir" | grep -oP 'iteration_\d+' | tail -1 || true)
    [[ -z "$iter_tag" ]] && iter_tag="run_$(date +%Y%m%d_%H%M%S)"

    # 1. Sync data to NERSC scratch (skip if caller already synced)
    if [[ -n "$remote_data_dir" ]]; then
        log_info "  Data in:  ${remote_data_dir} (pre-synced, skipping transfer)"
    else
        log_info "  Data in:  ${data_dir}"
        log_info "            → ${user}@${host}:${remote_base}/${model}_data_${iter_tag}"
        timer_start "${model}_sync_data_to_nersc"
        remote_data_dir=$(_sync_data_to_nersc "$data_dir" "${model}_data_${iter_tag}") || {
            timer_end "${model}_sync_data_to_nersc"; return 1
        }
        timer_end "${model}_sync_data_to_nersc"
    fi

    # 2. Prepare remote output dir
    local remote_output_dir="${remote_base}/${model}_output_${iter_tag}"
    ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" "mkdir -p '${remote_output_dir}'" || return 1

    # 3. Submit SLURM job with hybrid_ prefix so it's identifiable in squeue
    # NERSC_DEBUG=true → debug queue, minimal params, _debug script variant
    local slurm_script qos_override time_override
    if [[ "${NERSC_DEBUG:-false}" == "true" ]]; then
        slurm_script="${remote_work}/slurm/${model}_train_slurm_debug.sh"
        qos_override="--qos=debug --time=00:15:00"
        log_info "  [DEBUG] Using debug queue + minimal params"
    else
        slurm_script="${remote_work}/slurm/${model}_train_slurm.sh"
        qos_override=""
    fi

    log_info "  [submit] sbatch ${model}_train_slurm${NERSC_DEBUG:+_debug}.sh on ${host}"
    local sbatch_out sbatch_rc=0
    sbatch_out=$(ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" \
        "sbatch \
            --job-name='hybrid_${model}' \
            --output='${logs_dir}/hybrid_${model}_%j.out' \
            --error='${logs_dir}/hybrid_${model}_%j.err' \
            ${qos_override} \
            --export=ALL,WORK_DIR='${remote_work}',NERSC_TRAIN_WORK_DIR='${NERSC_TRAIN_WORK_DIR:-/global/homes/k/kurl/common/kurl_system/intheloop}',SENSPOT_SEND_MODELS='${SENSPOT_SEND_MODELS:-true}',SENSPOT_MODELS_ENDPOINT='${SENSPOT_MODELS_ENDPOINT:-woof://169.231.230.76/sharedfs/models}',SENSPOT_KEEP_ARCHIVES='${SENSPOT_KEEP_ARCHIVES:-false}' \
            '${slurm_script}' \
            '${remote_data_dir}' \
            '${remote_output_dir}' \
            2>&1") || sbatch_rc=$?
    if [[ $sbatch_rc -ne 0 ]]; then
        log_error "sbatch failed for ${model} on NERSC (exit ${sbatch_rc}):"
        log_error "${sbatch_out}"
        return 1
    fi
    local job_id
    job_id=$(echo "$sbatch_out" | awk '/Submitted batch job/{print $4}')
    if [[ -z "$job_id" || ! "$job_id" =~ ^[0-9]+$ ]]; then
        log_error "Failed to parse ${model} job ID from sbatch output:"
        log_error "${sbatch_out}"
        return 1
    fi
    log_info "  [submit ✓] job_id=${job_id}  name=hybrid_${model}  logs=${logs_dir}/hybrid_${model}_${job_id}.out"

    _record_hybrid_job_id "$model" "$job_id" "$remote_output_dir"
    echo "${job_id}:${remote_output_dir}"
}

# _nersc_collect_results <model> <job_id> <remote_output_dir> <local_output_dir>
# Waits for SLURM job to complete, then syncs results back.
_nersc_collect_results() {
    local model="$1"
    local job_id="$2"
    local remote_output_dir="$3"
    local local_output_dir="$4"

    local ssh_key="${NERSC_SSH_KEY:-${WORK_DIR}/nersc}"
    local user="${NERSC_USER:-kurl}"
    local host="${NERSC_SSH_HOST:-perlmutter.nersc.gov}"

    timer_start "${model}_nersc_job_wait"
    _wait_nersc_slurm_job "$job_id" || { timer_end "${model}_nersc_job_wait"; return 1; }
    timer_end "${model}_nersc_job_wait"

    log_info "  [sync ←] ${user}@${host}:${remote_output_dir} → ${local_output_dir}"
    timer_start "${model}_sync_results_back"
    mkdir -p "$local_output_dir"
    local rsync_out rsync_rc=0
    rsync_out=$(rsync -az --no-perms --stats \
        -e "ssh -i '${ssh_key}' -q -o BatchMode=yes -o StrictHostKeyChecking=no" \
        "${user}@${host}:${remote_output_dir}/" "${local_output_dir}/" 2>&1) || rsync_rc=$?
    if [[ $rsync_rc -ne 0 ]]; then
        log_warn "Failed to sync ${model} results back from NERSC (exit ${rsync_rc}):"
        log_warn "${rsync_out}"
        timer_end "${model}_sync_results_back"
        return 1
    fi
    echo "$rsync_out" | grep -E '^(Number of files|Total file size|Total transferred|sent |bytes/sec)' \
        | while IFS= read -r line; do log_info "  [rsync] ${line}"; done
    timer_end "${model}_sync_results_back"

    log_info "  [done ✓] ${model^^} artifacts: ${local_output_dir}"
}

# run_training_phase_hybrid <sim_output> <model_output_base>
# Hybrid training pipeline:
#   1. Sync slurm scripts to NERSC once
#   2. Submit all NERSC-bound models (PINN, FNO, ...) in sequence → get job IDs
#   3. Run UCSB-bound models (PCR, ...) while NERSC jobs are queued/running
#   4. Wait for all NERSC jobs and sync results back
run_training_phase_hybrid() {
    local sim_output="$1"
    local model_output_base="$2"

    # Determine which models go where
    local nersc_models=() racelab_models=() ucsb_models=()
    for model in $TRAIN_MODELS; do
        case "$(get_module_system "$model")" in
            nersc)   nersc_models+=("$model") ;;
            racelab) racelab_models+=("$model") ;;
            *)       ucsb_models+=("$model") ;;
        esac
    done

    log_section "HYBRID TRAINING: submit-all → run-ucsb → collect-all"
    log_info "  NERSC jobs:   ${nersc_models[*]:-none}"
    log_info "  Racelab jobs: ${racelab_models[*]:-none}"
    log_info "  UCSB jobs:    ${ucsb_models[*]:-none}"

    # Phase 0a: sync slurm scripts + sim data to NERSC once (shared across all NERSC models)
    local shared_nersc_data_dir=""
    if [[ ${#nersc_models[@]} -gt 0 ]]; then
        _sync_scripts_to_nersc || return 1

        local iter_tag
        iter_tag=$(echo "$sim_output" | grep -oP 'iteration_\d+' | tail -1 || true)
        [[ -z "$iter_tag" ]] && iter_tag="run_$(date +%Y%m%d_%H%M%S)"

        log_info "[hybrid] Syncing simulation data to NERSC once (shared by all NERSC models)..."
        timer_start "nersc_sync_shared_data"
        shared_nersc_data_dir=$(_sync_data_to_nersc "$sim_output" "shared_data_${iter_tag}") || return 1
        timer_end "nersc_sync_shared_data"
        log_info "[hybrid] Shared NERSC data at: ${shared_nersc_data_dir}"
    fi

    # Phase 0b: sync sim data to racelab once (shared across all racelab models)
    local shared_racelab_data_dir=""
    if [[ ${#racelab_models[@]} -gt 0 ]]; then
        local iter_tag_rl
        iter_tag_rl=$(echo "$sim_output" | grep -oP 'iteration_\d+' | tail -1 || true)
        [[ -z "$iter_tag_rl" ]] && iter_tag_rl="run_$(date +%Y%m%d_%H%M%S)"

        log_info "[hybrid] Syncing simulation data to racelab once (shared by all racelab models)..."
        timer_start "racelab_sync_shared_data"
        shared_racelab_data_dir=$(_sync_data_to_racelab "$sim_output" "shared_data_${iter_tag_rl}") || return 1
        timer_end "racelab_sync_shared_data"
        log_info "[hybrid] Shared racelab data at: ${shared_racelab_data_dir}"
    fi

    # Phase 1a: submit all NERSC jobs
    declare -A _nersc_job_ids _nersc_remote_dirs
    local submit_rc=0
    for model in "${nersc_models[@]}"; do
        log_section "HYBRID SUBMIT: ${model^^} (nersc)"
        local submit_result
        submit_result=$(_nersc_prepare_and_submit \
            "$model" "$sim_output" "${model_output_base}/${model}" \
            "$shared_nersc_data_dir") || { submit_rc=$?; break; }
        _nersc_job_ids[$model]="${submit_result%%:*}"
        _nersc_remote_dirs[$model]="${submit_result#*:}"
    done
    if [[ $submit_rc -ne 0 ]]; then
        log_error "NERSC job submission failed — aborting hybrid training phase"
        return 1
    fi

    # Phase 1b: submit all racelab jobs
    declare -A _racelab_pids _racelab_remote_dirs _racelab_log_files
    for model in "${racelab_models[@]}"; do
        log_section "HYBRID SUBMIT: ${model^^} (racelab)"
        local submit_result
        submit_result=$(_racelab_submit \
            "$model" "$sim_output" "${model_output_base}/${model}" \
            "$shared_racelab_data_dir") || { submit_rc=$?; break; }
        # format: pid:remote_output_dir:log_file
        _racelab_pids[$model]="${submit_result%%:*}"
        local rest="${submit_result#*:}"
        _racelab_remote_dirs[$model]="${rest%%:*}"
        _racelab_log_files[$model]="${rest#*:}"
        timer_start "${model}_racelab_wall"
    done
    if [[ $submit_rc -ne 0 ]]; then
        log_error "Racelab job submission failed — aborting hybrid training phase"
        return 1
    fi

    # Phase 2: run UCSB models while remote jobs are running
    for model in "${ucsb_models[@]}"; do
        run_training "$model" "$sim_output" "${model_output_base}/${model}" || return 1
    done

    # Phase 3a: wait for all NERSC jobs and collect results
    local collect_rc=0
    for model in "${nersc_models[@]}"; do
        local job_id="${_nersc_job_ids[$model]}"
        local remote_dir="${_nersc_remote_dirs[$model]}"
        local local_dir="${model_output_base}/${model}"
        log_section "HYBRID COLLECT: ${model^^} (nersc job_id=${job_id})"
        _nersc_collect_results "$model" "$job_id" "$remote_dir" "$local_dir" || collect_rc=$?
        # senspot archiving runs inside the SLURM job on NERSC — no local send needed
    done

    # Phase 3b: wait for all racelab jobs and collect results
    for model in "${racelab_models[@]}"; do
        local pid="${_racelab_pids[$model]}"
        local log_file="${_racelab_log_files[$model]}"
        local remote_dir="${_racelab_remote_dirs[$model]}"
        local local_dir="${model_output_base}/${model}"
        log_section "HYBRID COLLECT: ${model^^} (racelab pid=${pid})"
        _racelab_collect_results "$model" "$pid" "$log_file" "$remote_dir" "$local_dir" || collect_rc=$?
        timer_end "${model}_racelab_wall"

        # Send model to woof after collection (mandatory regardless of where training ran)
        if [[ $collect_rc -eq 0 ]]; then
            local iteration="unknown"
            if [[ "$local_dir" =~ iteration_([0-9]+) ]]; then
                iteration="${BASH_REMATCH[1]}"
            fi
            archive_and_send_model "$model" "$local_dir" "$iteration"
        fi
    done

    return $collect_rc
}

################################################################################
# Hybrid Racelab primitives: submit, wait, collect
################################################################################

# _sync_data_to_racelab <local_dir> <remote_label>
# Rsyncs a local directory to racelab-gpu1.
# Echoes the remote absolute path on success.
_sync_data_to_racelab() {
    local local_dir="$1"
    local remote_label="${2:-data}"

    local ssh_key="${RACELAB_SSH_KEY:-${WORK_DIR}/racelabgpu}"
    local user="${RACELAB_USER:-liubov_kurafeeva}"
    local host="${RACELAB_SSH_HOST:-rw-gpu1.cs.ucsb.edu}"
    local remote_base="${RACELAB_REMOTE_WORK_DIR:-/local/home/liubov_kurafeeva/intheloop_hybrid}"
    local remote_dir="${remote_base}/${remote_label}"

    log_info "  [sync →] ${local_dir}"
    log_info "  [sync →] ${user}@${host}:${remote_dir}"

    ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" "mkdir -p '${remote_dir}'" || {
        log_error "Failed to create remote directory: ${remote_dir}"
        return 1
    }

    local rsync_out rsync_rc=0
    rsync_out=$(rsync -az --delete --no-perms --stats \
        -e "ssh -i '${ssh_key}' -q -o BatchMode=yes -o StrictHostKeyChecking=no" \
        "${local_dir}/" "${user}@${host}:${remote_dir}/" 2>&1) || rsync_rc=$?
    # Exit code 24 = "some files vanished before they could be transferred" (rsync warning, not error).
    # Race condition: background SSH log-writing processes close their files between rsync's
    # file-list scan and the actual transfer. All files present at transfer time were synced
    # successfully — treat as non-fatal.
    if [[ $rsync_rc -eq 24 ]]; then
        log_warn "rsync to racelab: some files vanished during transfer (exit 24) — non-fatal, continuing"
        log_warn "  ${local_dir} -> ${remote_dir}"
        rsync_rc=0
    fi
    if [[ $rsync_rc -ne 0 ]]; then
        log_error "rsync to racelab failed (exit ${rsync_rc}): ${local_dir} -> ${remote_dir}"
        log_error "${rsync_out}"
        return 1
    fi
    echo "$rsync_out" | grep -E '^(Number of files|Total file size|Total transferred|sent |bytes/sec)' \
        | while IFS= read -r line; do log_info "  [rsync] ${line}"; done

    log_info "  [sync ✓] Data available at: ${remote_dir}"
    echo "$remote_dir"
}

# _racelab_submit <model> <data_dir> <local_output_dir> [remote_data_dir]
# Runs a training job directly on racelab-gpu1 via nohup SSH (no queue).
# Prints "pid:remote_output_dir" to stdout on success.
_racelab_submit() {
    local model="$1"
    local data_dir="$2"
    local local_output_dir="$3"
    local remote_data_dir="${4:-}"

    local ssh_key="${RACELAB_SSH_KEY:-${WORK_DIR}/racelabgpu}"
    local user="${RACELAB_USER:-liubov_kurafeeva}"
    local host="${RACELAB_SSH_HOST:-rw-gpu1.cs.ucsb.edu}"
    local remote_base="${RACELAB_REMOTE_WORK_DIR:-/local/home/liubov_kurafeeva/intheloop_hybrid}"
    local logs_dir="${RACELAB_LOGS_DIR:-/local/home/liubov_kurafeeva/jobs_logs}"
    local conda_env="${RACELAB_CONDA_ENV:-cfdai_tf310}"

    local iter_tag
    iter_tag=$(echo "$data_dir" | grep -oP 'iteration_\d+' | tail -1 || true)
    [[ -z "$iter_tag" ]] && iter_tag="run_$(date +%Y%m%d_%H%M%S)"

    # 1. Sync data to racelab (skip if pre-synced)
    if [[ -n "$remote_data_dir" ]]; then
        log_info "  Data in:  ${remote_data_dir} (pre-synced, skipping transfer)"
    else
        log_info "  Data in:  ${data_dir}"
        timer_start "${model}_sync_data_to_racelab"
        remote_data_dir=$(_sync_data_to_racelab "$data_dir" "${model}_data_${iter_tag}") || {
            timer_end "${model}_sync_data_to_racelab"; return 1
        }
        timer_end "${model}_sync_data_to_racelab"
    fi

    # 2. Sync training scripts to racelab (model dir + shared cfd_common.py)
    local remote_scripts="${remote_base}/scripts"
    log_info "  [sync →] training scripts → ${user}@${host}:${remote_scripts}"
    ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" "mkdir -p '${remote_scripts}/training/${model}' '${logs_dir}'"
    rsync -az --no-perms \
        -e "ssh -i '${ssh_key}' -q -o BatchMode=yes -o StrictHostKeyChecking=no" \
        "${WORK_DIR}/training/${model}/" "${user}@${host}:${remote_scripts}/training/${model}/" 2>&1 \
        | grep -E '^(Number of|sent )' | while IFS= read -r line; do log_info "  [rsync] ${line}"; done || true
    # Also sync shared cfd_common.py so model scripts can import it
    if [[ -f "${WORK_DIR}/training/cfd_common.py" ]]; then
        rsync -az --no-perms \
            -e "ssh -i '${ssh_key}' -q -o BatchMode=yes -o StrictHostKeyChecking=no" \
            "${WORK_DIR}/training/cfd_common.py" \
            "${user}@${host}:${remote_scripts}/training/${model}/cfd_common.py" 2>/dev/null || true
    fi

    # 3. Prepare remote output dir
    local remote_output_dir="${remote_base}/${model}_output_${iter_tag}"
    ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" "mkdir -p '${remote_output_dir}'" || return 1

    # 4. Build the train command (PYTHONPATH includes model dir for shared imports)
    # Each model has different argument conventions:
    #   pinn: positional csv_dir model_name  --output_dir DIR
    #   fno:  --data-dir DIR  --output-dir DIR
    local log_file="${logs_dir}/racelab_${model}_${iter_tag}.log"
    local train_script="training/${model}/train_${model}.py"
    local pythonpath="PYTHONPATH='${remote_scripts}/training/${model}:\${PYTHONPATH:-}'"
    local train_cmd
    case "$model" in
        pinn)
            train_cmd="${pythonpath} python3 '${remote_scripts}/${train_script}' '${remote_data_dir}' '${model}' --output_dir '${remote_output_dir}' --max_points_per_file 5000 --epochs 200 --patience 60"
            ;;
        fno)
            train_cmd="${pythonpath} python3 '${remote_scripts}/${train_script}' --data-dir '${remote_data_dir}' --output-dir '${remote_output_dir}' --epochs 60 --patience 30"
            ;;
        *)
            train_cmd="${pythonpath} python3 '${remote_scripts}/${train_script}' --data '${remote_data_dir}' --output '${remote_output_dir}'"
            ;;
    esac

    # 5. Launch via nohup, capture PID
    log_info "  [submit] nohup ${model} training on ${host} (direct, no queue)"
    local pid
    pid=$(ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" "
            set -e
            # Find conda init script
            CONDA_INIT=\"\"
            for p in \"\$HOME/miniconda3\" \"\$HOME/miniforge3\" \"\$HOME/anaconda3\" \"/opt/conda\"; do
                if [[ -f \"\${p}/etc/profile.d/conda.sh\" ]]; then
                    CONDA_INIT=\"\${p}/etc/profile.d/conda.sh\"
                    break
                fi
            done
            # Build the full launch command using conda run (works in non-interactive SSH)
            FULL_CMD=\"LD_LIBRARY_PATH=/usr/local/cuda-12.2/targets/sbsa-linux/lib:/usr/local/cuda-12.2/lib64:/usr/lib/aarch64-linux-gnu TF_CPP_MIN_LOG_LEVEL=2 TF_FORCE_GPU_ALLOW_GROWTH=true ${train_cmd}\"
            if [[ -n \"\$CONDA_INIT\" ]]; then
                source \"\$CONDA_INIT\"
                LAUNCH=\"conda run -n ${conda_env} bash -c '\$FULL_CMD'\"
            else
                LAUNCH=\"bash -c '\$FULL_CMD'\"
            fi
            nohup bash -c \"\$LAUNCH\" > '${log_file}' 2>&1 &
            echo \$!
        " 2>/dev/null) || {
        log_error "Failed to launch ${model} training on racelab"
        return 1
    }

    if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]]; then
        log_error "Could not capture PID for ${model} on racelab (got: '${pid}')"
        return 1
    fi

    log_info "  [submit ✓] pid=${pid}  log=${log_file}"
    echo "${pid}:${remote_output_dir}:${log_file}"
}

# _wait_racelab_job <pid> <log_file>
# Polls racelab every 30s until the process (by PID) exits.
# Returns 0 if process exited cleanly (log contains no ERROR/Traceback), 1 otherwise.
# Honors RACELAB_JOB_TIMEOUT_SECONDS (default: 14400 = 4h). On timeout, kills
# the tracked PID and its children on racelab before returning 1.
_wait_racelab_job() {
    local pid="$1"
    local log_file="$2"

    local ssh_key="${RACELAB_SSH_KEY:-${WORK_DIR}/racelabgpu}"
    local user="${RACELAB_USER:-liubov_kurafeeva}"
    local host="${RACELAB_SSH_HOST:-rw-gpu1.cs.ucsb.edu}"
    local timeout_secs="${RACELAB_JOB_TIMEOUT_SECONDS:-14400}"
    local poll_start
    poll_start=$(date +%s)

    log_info "  [wait] Polling racelab PID ${pid} every 30s (timeout: $(( timeout_secs / 60 ))m)..."

    while true; do
        local elapsed=$(( $(date +%s) - poll_start ))

        # Timeout: kill the job on racelab and bail
        if [[ $elapsed -ge $timeout_secs ]]; then
            log_warn "  [wait] Timeout reached ($(( elapsed / 60 ))m), killing racelab PID ${pid} and children..."
            ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
                -o ConnectTimeout=15 \
                "${user}@${host}" \
                "kill \$(pgrep -P ${pid} 2>/dev/null) 2>/dev/null; kill ${pid} 2>/dev/null; true" || true
            log_error "  [wait ✗] racelab PID ${pid} killed after timeout ($(format_duration $elapsed))"
            return 1
        fi

        local alive=0
        # ConnectTimeout ensures a transient SSH hiccup doesn't look like process exit
        ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
            -o ConnectTimeout=15 \
            "${user}@${host}" "kill -0 ${pid} 2>/dev/null" && alive=1 || alive=0
        if [[ $alive -eq 0 ]]; then
            break
        fi
        log_info "  [wait] PID ${pid} running... $(( elapsed / 60 ))m elapsed"
        sleep 30
    done

    local total_wait=$(( $(date +%s) - poll_start ))

    # Check log for errors
    local tail_out
    tail_out=$(ssh -i "$ssh_key" -q -o BatchMode=yes -o StrictHostKeyChecking=no \
        "${user}@${host}" "tail -40 '${log_file}' 2>/dev/null" 2>/dev/null || echo "")

    if echo "$tail_out" | grep -qiE 'Traceback|Error:|FAILED'; then
        log_error "  [wait ✗] racelab PID ${pid} finished with errors (waited $(format_duration $total_wait))"
        log_error "  [log tail] ${log_file} (last 40 lines):"
        echo "$tail_out" | while IFS= read -r line; do log_error "    ${line}"; done
        return 1
    fi

    log_info "  [wait ✓] racelab PID ${pid} completed (waited $(format_duration $total_wait))"
    return 0
}

# _racelab_collect_results <model> <pid> <log_file> <remote_output_dir> <local_output_dir>
# Waits for the racelab job to finish, then syncs results back.
_racelab_collect_results() {
    local model="$1"
    local pid="$2"
    local log_file="$3"
    local remote_output_dir="$4"
    local local_output_dir="$5"

    local ssh_key="${RACELAB_SSH_KEY:-${WORK_DIR}/racelabgpu}"
    local user="${RACELAB_USER:-liubov_kurafeeva}"
    local host="${RACELAB_SSH_HOST:-rw-gpu1.cs.ucsb.edu}"

    timer_start "${model}_racelab_job_wait"
    _wait_racelab_job "$pid" "$log_file" || { timer_end "${model}_racelab_job_wait"; return 1; }
    timer_end "${model}_racelab_job_wait"

    log_info "  [sync ←] ${user}@${host}:${remote_output_dir} → ${local_output_dir}"
    timer_start "${model}_sync_results_back"
    mkdir -p "$local_output_dir"
    local rsync_out rsync_rc=0
    rsync_out=$(rsync -az --no-perms --stats \
        -e "ssh -i '${ssh_key}' -q -o BatchMode=yes -o StrictHostKeyChecking=no" \
        "${user}@${host}:${remote_output_dir}/" "${local_output_dir}/" 2>&1) || rsync_rc=$?
    if [[ $rsync_rc -ne 0 ]]; then
        log_warn "Failed to sync ${model} results back from racelab (exit ${rsync_rc}):"
        log_warn "${rsync_out}"
        timer_end "${model}_sync_results_back"
        return 1
    fi
    echo "$rsync_out" | grep -E '^(Number of files|Total file size|Total transferred|sent |bytes/sec)' \
        | while IFS= read -r line; do log_info "  [rsync] ${line}"; done
    timer_end "${model}_sync_results_back"

    log_info "  [done ✓] ${model^^} artifacts: ${local_output_dir}"
}

# Legacy single-job wrappers (kept for manual/debug dispatch via run_training)
_run_pinn_nersc_via_ssh() {
    local data_dir="$1"
    local output_dir="$2"

    log_section "HYBRID MODULE: PINN Training"
    if ! check_nersc_connectivity; then
        log_error "NERSC not reachable — cannot dispatch PINN training"
        return 1
    fi
    _sync_scripts_to_nersc || return 1

    local submit_result
    submit_result=$(_nersc_prepare_and_submit "pinn" "$data_dir" "$output_dir") || return 1
    local job_id remote_output_dir
    job_id="${submit_result%%:*}"
    remote_output_dir="${submit_result#*:}"

    _nersc_collect_results "pinn" "$job_id" "$remote_output_dir" "$output_dir"
}

_run_fno_nersc_via_ssh() {
    local data_dir="$1"
    local output_dir="$2"

    log_section "HYBRID MODULE: FNO Training"
    if ! check_nersc_connectivity; then
        log_error "NERSC not reachable — cannot dispatch FNO training"
        return 1
    fi
    _sync_scripts_to_nersc || return 1

    local submit_result
    submit_result=$(_nersc_prepare_and_submit "fno" "$data_dir" "$output_dir") || return 1
    local job_id remote_output_dir
    job_id="${submit_result%%:*}"
    remote_output_dir="${submit_result#*:}"

    _nersc_collect_results "fno" "$job_id" "$remote_output_dir" "$output_dir"
}

################################################################################
# Training Status
################################################################################

check_training_status() {
    local model_type="${1:-all}"
    
    case "$SYSTEM_TYPE" in
        nersc)
            if [[ "$model_type" == "all" ]]; then
                squeue -u "$USER" --name="pcr_train,pinn_train,fno_train"
            else
                squeue -u "$USER" --name="${model_type}_train"
            fi
            ;;
        *)
            # Check for running processes
            pgrep -f "train_${model_type}" || true
            ;;
    esac
}
