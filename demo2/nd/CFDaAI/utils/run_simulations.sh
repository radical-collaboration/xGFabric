#!/bin/bash
set -eo pipefail

# Load user config if it exists
CONFIG_FILE="${WORK_DIR}/config.sh"
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

# Load system libraries
source "${WORK_DIR}/lib/common.sh"
source "${WORK_DIR}/env/system_config.sh"

detect_system
detect_features

export STATUS_FILE="${LOGS_DIR}/coordinator/workflow_status_log.csv"
bash ${WORK_DIR}/utils/csv_logger.sh "${WORKFLOW_NUMBER}" "simulation_phase" "started" "${STATUS_FILE}"

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

simulation_makeflow() {
    log_info "Submitting ${num_sims} simulations to UGE..."

    makeflow_file="${LOGS_DIR}/workflows/${WORKFLOW_NUMBER}/simulations/openfoam_tasks.makeflow"

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

    python3 ${WORK_DIR}/utils/make_sim_workflow.py ${num_sims} ${makeflow_file} ${SIMULATION_THREADS} ${WORK_DIR} ${param_dir} ${sim_output}

    bash ${WORK_DIR}/utils/csv_logger.sh "${WORKFLOW_NUMBER}" "openfoam_sim" "submitted" "${STATUS_FILE}"
    
    makeflow -T uge ${WORKFLOW_LOCATION}/simulations/openfoam_tasks.makeflow
}

log_section "Simulation Phase"

# Phase 2: Run simulations
log_subsection "Simulations"
timer_start "simulations"
start_ram_monitor "OpenFOAM Simulations"

param_dir="${RESULTS_DIR}/params"
sim_output="${RESULTS_DIR}/simulations"

sim_params_file="${param_dir}/sim_params.csv"
require_file "$sim_params_file" "Simulation parameters file"

# Count simulations (skip header)
num_sims=$(tail -n +2 "$sim_params_file" | wc -l)

simulation_makeflow

stop_ram_monitor "OpenFOAM Simulations"
timer_end "simulations"
bash ${WORK_DIR}/utils/csv_logger.sh "${WORKFLOW_NUMBER}" "simulation_phase" "completed" "${STATUS_FILE}"
