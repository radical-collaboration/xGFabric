#!/bin/bash
set -eo pipefail

# Load user config if it exists
CONFIG_FILE="${WORK_DIR}/config.sh"
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

# Load system libraries
source "${WORK_DIR}/lib/common.sh"
source "${WORK_DIR}/data/data_source.sh"
source "${WORK_DIR}/training/orchestrate_training.sh"
source "${WORK_DIR}/env/system_config.sh"

detect_system
detect_features

# Set defaults from config (CLI args take precedence over config.sh)
CONVERGENCE_THRESHOLD="${CONVERGENCE_THRESHOLD:-0.01}"
# User CLI --models takes precedence, then env/config, default to pcr
TRAIN_MODELS="${USER_TRAIN_MODELS:-${TRAIN_MODELS:-pcr}}"

# Start logging
export STATUS_FILE="${LOGS_DIR}/coordinator/workflow_status_log.csv"
python3 ${WORK_DIR}/utils/csv_logger.py "${WORKFLOW_NUMBER}" "training_phase" "started" "${STATUS_FILE}"

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

training_makeflow() {
    makeflow_file="${LOGS_DIR}/workflows/${WORKFLOW_NUMBER}/training/training.makeflow"

    if ! [ -f "$makeflow_file" ]; then
        echo "WORK_DIR=${WORK_DIR}"                     >> "$makeflow_file"
        echo "WORKFLOW_NUMBER=${WORKFLOW_NUMBER}"       >> "$makeflow_file"
        echo "WORKFLOW_LOCATION=${WORKFLOW_LOCATION}"   >> "$makeflow_file"
        echo "RESULTS_DIR=${RESULTS_DIR}"               >> "$makeflow_file"
        echo "LOGS_DIR=${LOGS_DIR}"                     >> "$makeflow_file"
        echo "SIMULATION_THREADS=${SIMULATION_THREADS}" >> "$makeflow_file"
        echo "STATUS_FILE=${STATUS_FILE}"               >> "$makeflow_file"
        echo ""                                         >> "$makeflow_file"
        echo "export WORK_DIR"                          >> "$makeflow_file"
        echo "export WORKFLOW_NUMBER"                   >> "$makeflow_file"
        echo "export WORKFLOW_LOCATION"                 >> "$makeflow_file"
        echo "export RESULTS_DIR"                       >> "$makeflow_file"
        echo "export LOGS_DIR"                          >> "$makeflow_file"
        echo "export SIMULATION_THREADS"                >> "$makeflow_file"
        echo "export STATUS_FILE"                       >> "$makeflow_file"

        python3 ${WORK_DIR}/utils/make_training_workflow.py "${TRAIN_MODELS}" ${makeflow_file} ${SIMULATION_THREADS} ${WORK_DIR}
    fi
    
    for model in $TRAIN_MODELS; do
        python3 ${WORK_DIR}/utils/csv_logger.py "${WORKFLOW_NUMBER}" "${model}_train" "submitted" "${STATUS_FILE}"
    done

    makeflow -T uge "$makeflow_file"
}

# Phase 3: Train models
log_subsection "Training"
timer_start "training"
start_ram_monitor "Training"

sim_output="${RESULTS_DIR}/simulations"
data_output="${RESULTS_DIR}/data"
model_output="${RESULTS_DIR}/models"

log_subsection "Training"

ensure_dir "$model_output"

# Set sensor data dir for training
if [[ -n "$USE_SENSOR_DIR" ]]; then
    export SENSOR_DATA_DIR="$USE_SENSOR_DIR"
elif [[ -n "$USE_DATA_DIR" ]]; then
    export SENSOR_DATA_DIR="$USE_DATA_DIR"
else
    export SENSOR_DATA_DIR="$data_output"
fi

log_info "Using simulation data: ${sim_output}"
log_info "Using sensor data: ${SENSOR_DATA_DIR}"

training_makeflow "$sim_output" "${model_output}/${model}"

for model in $TRAIN_MODELS; do
    archive_and_send_model "$model" "$model_output/$model"
done

stop_ram_monitor "Training"
timer_end "training"

log_info "Done."
python3 ${WORK_DIR}/utils/csv_logger.py "${WORKFLOW_NUMBER}" "training_phase" "completed" "${STATUS_FILE}"
