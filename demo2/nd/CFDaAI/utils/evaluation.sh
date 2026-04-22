#!/bin/bash
set -eo pipefail

# Load user config if it exists
CONFIG_FILE="${WORK_DIR}/config.sh"
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

# Load system libraries
source "${WORK_DIR}/env/system_config.sh"
source "${WORK_DIR}/lib/common.sh"

export STATUS_FILE="${LOGS_DIR}/coordinator/workflow_status_log.csv"
python3 ${WORK_DIR}/utils/csv_logger.py "${WORKFLOW_NUMBER}" "evaluation_phase" "started" "${STATUS_FILE}"

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

_validate_sensor_cutoff() {
    local sensor_file="$1"
    local cutoff="$2"
    python3 "${WORK_DIR}/utils/validate_sensor_cutoff.py" "$sensor_file" "$cutoff"
}

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
        "$HOME/cspot/build/bin"
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
# Args: model_type output_dir
archive_and_send_model() {
    local model_type="$1"
    local output_dir="$2"
    
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
    
    # Generate archive filename with timestamp
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local archive_name="${model_type}_${timestamp}.tar.gz"
    local archive_path="${archive_dir}/${archive_name}"
    
    # Determine which files to archive based on model type
    local files_to_archive=()
    
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
    local relative_files=()
    for file in "${files_to_archive[@]}"; do
        # Use path relative to output_dir, not just basename
        local rel_path="${file#$output_dir/}"
        relative_files+=("$rel_path")
    done

    if tar -czf "$archive_path" -C "$output_dir" "${relative_files[@]}"; then
        local archive_size=$(du -h "$archive_path" | cut -f1)
        log_info "✓ Created archive: ${archive_name} (${archive_size})"
        for csv_file in "${relative_files[@]}"; do
            rm -rf "${csv_file}"
        done
        log_info "Removed related files to save space"
    else
        log_error "✗ Failed to create archive: ${archive_path}"
        return 1
    fi
    
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


# Phase 4: Evaluate
log_subsection "Evaluation"
timer_start "evaluation"

model_output="${RESULTS_DIR}/models"
data_dir="${USE_SENSOR_DIR:-${RESULTS_DIR}/data}"
eval_output="${RESULTS_DIR}/evaluation"

log_subsection "Evaluation"

ensure_dir "$eval_output"

for model in $TRAIN_MODELS; do
    archive_and_send_model "$model" "$model_output/$model"
done

# Calculate basic sensor data metrics
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

timer_end "evaluation"

# Print timing summary
log_section "Pipeline Complete"

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
    short_info="$(echo "${TRAIN_MODELS}" | tr ' ' '-')"
    archive_results "$RESULTS_DIR" "$short_info"
fi

log_info "Done."
python3 ${WORK_DIR}/utils/csv_logger.py "${WORKFLOW_NUMBER}" "evaluation_phase" "completed" "${STATUS_FILE}"
python3 ${WORK_DIR}/utils/csv_logger.py "${WORKFLOW_NUMBER}" "workflow" "exited" "${STATUS_FILE}"
