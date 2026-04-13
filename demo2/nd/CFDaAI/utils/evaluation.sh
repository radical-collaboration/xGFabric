#!/bin/bash
set -eo pipefail

# Load user config if it exists
CONFIG_FILE="${WORK_DIR}/config.sh"
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

# Load system libraries
source "${WORK_DIR}/env/system_config.sh"
source "${WORK_DIR}/lib/common.sh"

export STATUS_FILE="${LOGS_DIR}/coordinator/workflow_status_log.csv"
bash ${WORK_DIR}/utils/csv_logger.sh "${WORKFLOW_NUMBER}" "evaluation_phase" "started" "${STATUS_FILE}"

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

# Phase 4: Evaluate
log_subsection "Evaluation"
timer_start "evaluation"

model_output="${RESULTS_DIR}/models"
data_dir="${USE_SENSOR_DIR:-${RESULTS_DIR}/data}"
eval_output="${RESULTS_DIR}/evaluation"

log_subsection "Evaluation"

ensure_dir "$eval_output"

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
bash ${WORK_DIR}/utils/csv_logger.sh "${WORKFLOW_NUMBER}" "evaluation_phase" "completed" "${STATUS_FILE}"
bash ${WORK_DIR}/utils/csv_logger.sh "${WORKFLOW_NUMBER}" "workflow" "exited" "${STATUS_FILE}"
