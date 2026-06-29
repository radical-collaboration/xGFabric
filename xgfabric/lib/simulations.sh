#!/bin/bash
#
# simulations.sh - Simulation orchestration
#
# Manages running OpenFOAM simulations across different execution modes
#
# Usage:
#   source lib/simulations.sh
#   run_simulations <params_file> <output_dir>

################################################################################
# Simulation Parameter Generation
################################################################################

generate_sim_params() {
    local output_file="$1"
    local wind_speed_min="$2"
    local wind_speed_max="$3"
    local wind_dir="${4:-0}"
    local num_sims="${5:-10}"
    
    log_info "Generating simulation parameters (interpolated mode)..."
    log_info "  Wind speed: ${wind_speed_min} - ${wind_speed_max} m/s"
    log_info "  Wind direction: ${wind_dir}°"
    log_info "  Number of simulations: ${num_sims}"
    
    # Header
    echo "wind_speed,wind_dir" > "$output_file"
    
    # Calculate step
    local range=$(echo "$wind_speed_max - $wind_speed_min" | bc)
    local step=$(echo "scale=2; $range / ($num_sims - 1)" | bc)
    
    for i in $(seq 0 $((num_sims - 1))); do
        local ws=$(echo "scale=2; $wind_speed_min + $i * $step" | bc)
        echo "${ws},${wind_dir}" >> "$output_file"
    done
    
    log_info "Parameters saved to: ${output_file}"
}

generate_sim_params_from_sensor() {
    local output_file="$1"
    local sensor_csv="$2"
    local max_sims="${3:-50}"
    
    log_info "Generating simulation parameters from sensor data (direct mode)..."
    log_info "  Source: ${sensor_csv}"
    log_info "  Max simulations: ${max_sims}"
    
    if [[ ! -f "$sensor_csv" ]]; then
        log_error "Sensor CSV not found: ${sensor_csv}"
        return 1
    fi
    
    # Use Python to extract unique wind speed/direction pairs from sensor data
    python3 "${WORK_DIR}/utils/sensor_to_sim_params.py" "$sensor_csv" "$output_file" "$max_sims"
    
    if [[ $? -eq 0 ]]; then
        log_info "Parameters saved to: ${output_file}"
        return 0
    else
        log_error "Failed to generate parameters from sensor data"
        return 1
    fi
}

