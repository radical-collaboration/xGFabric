#!/bin/bash
set -eo pipefail

export STATUS_FILE="${LOGS_DIR}/coordinator/workflow_status_log.csv"
bash ${WORK_DIR}/utils/csv_logger.sh "${WORKFLOW_NUMBER}" "workflow" "started" "${STATUS_FILE}"

# Load user config if it exists
CONFIG_FILE="${WORK_DIR}/config.sh"
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

# Load system libraries
source "${WORK_DIR}/env/system_config.sh"
source "${WORK_DIR}/lib/common.sh"
source "${WORK_DIR}/lib/simulations.sh"
source "${WORK_DIR}/data/data_source.sh"

# Source grid configuration
if [[ -f "${WORK_DIR}/training/pcr/read_grid_config.sh" ]]; then
    source "${WORK_DIR}/training/pcr/read_grid_config.sh"
fi

detect_system
detect_features
    
log_info "System initialization complete"

# Create directories
ensure_dir "$RESULTS_DIR"
ensure_dir "$LOGS_DIR"

# Start logging
bash ${WORK_DIR}/utils/csv_logger.sh "${WORKFLOW_NUMBER}" "data_gathering" "started" "${STATUS_FILE}"

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

run_simulation_phase() {
    local sim_output="${RESULTS_DIR}/simulations"
    local param_dir="${RESULTS_DIR}/params"
    
    log_subsection "Simulations"
    
    ensure_dir "$sim_output"
    ensure_dir "$param_dir"
    
    # Generate simulation parameters from sensor data
    local data_dir="${RESULTS_DIR}/data"
    
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


    local params_file="${param_dir}/sim_params.csv"
    local params_dir
    params_dir="$(dirname "$params_file")"
    
    log_info "Generating per-task JSON parameter files in: ${params_dir}"
    python3 "${WORK_DIR}/utils/generate_params.py" "$params_file" "$params_dir"
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to generate per-task JSON files from: ${params_file}"
        return 1
    fi
    
}

log_section "Get Data"
log_info "System: ${SYSTEM_TYPE}"
log_info "Workflow number: ${WORKFLOW_NUMBER}"

# Display system information
log_info "Available memory: $(get_available_memory_gb)GB"
log_info "Available disk: $(get_available_disk_gb "$WORK_DIR")GB"
if [[ -n "${DATA_CUTOFF_DATE:-}" ]]; then
    log_info "Data cutoff: ${DATA_CUTOFF_DATE}"
fi


workflow_dir="${RESULTS_DIR}"
ensure_dir "$workflow_dir"

# Phase 1: Fetch data
log_subsection "Data Acquisition"
timer_start "data_acquisition"
fetch_sensor_data "${workflow_dir}/data" "${DATA_CUTOFF_DATE:-}"
timer_end "data_acquisition"

log_section "Simulation Phase"

# Phase 2: Run simulations
log_subsection "Simulations"
timer_start "simulations"
start_ram_monitor "OpenFOAM Simulations"

run_simulation_phase

stop_ram_monitor "OpenFOAM Simulations"
timer_end "simulations"

bash ${WORK_DIR}/utils/csv_logger.sh "${WORKFLOW_NUMBER}" "data_gathering" "completed" "${STATUS_FILE}"

