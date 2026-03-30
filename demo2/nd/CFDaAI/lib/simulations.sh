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
# Main Entry Point
################################################################################

run_simulations() {
    local sim_params_file="$1"
    local output_dir="$2"
    local cores_per_sim="${3:-32}"
    
    # Validate inputs
    require_file "$sim_params_file" "Simulation parameters file"
    ensure_dir "$output_dir"
    
    # Count simulations (skip header)
    local num_sims=$(tail -n +2 "$sim_params_file" | wc -l)
    log_info "Preparing ${num_sims} simulations..."
    
    timer_start "simulations"
    
    # Determine execution mode
    if [[ "$SYSTEM_TYPE" == "nersc" ]]; then
        _run_simulations_slurm "$sim_params_file" "$output_dir" "$num_sims" "$cores_per_sim"

    elif [[ "$HAS_MACHINE_LIST" == "true" ]]; then
        _run_simulations_ssh "$sim_params_file" "$output_dir" "$num_sims" "$cores_per_sim"

    elif [[ "$SYSTEM_TYPE" == "nd" ]]; then
        _run_simulations_nd "$sim_params_file" "$output_dir" "$num_sims" "$cores_per_sim"

    else
        _run_simulations_local "$sim_params_file" "$output_dir" "$num_sims" "$cores_per_sim"
    fi
    
    timer_end "simulations"
}

################################################################################
# SLURM Array Jobs (NERSC)
################################################################################

_run_simulations_slurm() {
    local params_file="$1"
    local output_dir="$2"
    local num_sims="$3"
    local cores="$4"
    
    log_info "Submitting ${num_sims} simulations as SLURM array job..."
    
    # Generate individual sim_N.json files that simulation_slurm.sh expects.
    # simulation_slurm.sh picks PARAM_FILES[$SLURM_ARRAY_TASK_ID] from a directory;
    # the CSV has all params in one file so we expand them here before submission.
    local params_dir
    params_dir="$(dirname "$params_file")"
    
    log_info "Generating per-task JSON parameter files in: ${params_dir}"
    python3 "${WORK_DIR}/utils/generate_slurm_params.py" "$params_file" "$params_dir"
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to generate per-task JSON files from: ${params_file}"
        return 1
    fi
    
    # Export for SLURM script (kept for reference / backwards compat)
    export SIM_PARAMS_FILE="$params_file"
    export SIM_OUTPUT_DIR="$output_dir"
    export CORES_PER_SIM="$cores"
    
    local max_array_idx=$((num_sims - 1))
    local max_concurrent="${MAX_CONCURRENT_SIMS:-10}"
    
    local job_id
    # Pass params_dir and output_dir as positional $1/$2 to simulation_slurm.sh
    job_id=$(sbatch --parsable \
             --array="0-${max_array_idx}%${max_concurrent}" \
             --output="${SLURM_LOGS_DIR}/cfd_sim_array_%A_%a.out" \
             --error="${SLURM_LOGS_DIR}/cfd_sim_array_%A_%a.err" \
             --export=ALL \
             "${WORK_DIR}/slurm/simulation_slurm.sh" \
             "$params_dir" "$output_dir")
    
    if [[ $? -eq 0 ]]; then
        JOB_IDS["simulation"]="$job_id"
        log_info "Submitted simulation array job: ${job_id}"
        log_info "  Array range: 0-${max_array_idx}"
        log_info "  Max concurrent: ${max_concurrent}"
        log_info "  Params dir: ${params_dir}"
        log_info "  Output dir: ${output_dir}"
    else
        log_error "Failed to submit simulation array job"
        return 1
    fi
}


################################################################################
# UGE Array Jobs (ND)
################################################################################

_run_simulations_nd() {
    local params_file="$1"
    local output_dir="$2"
    local num_sims="$3"
    local cores="$4"
    
    log_info "Submitting ${num_sims} simulations as UGE array job..."

    # Generate individual sim_N.json files that simulation_uge.sh expects.
    # simulation_uge.sh picks PARAM_FILES[$UGE_ARRAY_TASK_ID] from a directory;
    # the CSV has all params in one file so we expand them here before submission.
    local params_dir
    params_dir="$(dirname "$params_file")"
    
    log_info "Generating per-task JSON parameter files in: ${params_dir}"
    python3 "${WORK_DIR}/utils/generate_uge_params.py" "$params_file" "$params_dir"
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to generate per-task JSON files from: ${params_file}"
        return 1
    fi

    local max_array_idx=$((num_sims))
    local max_concurrent="${MAX_CONCURRENT_SIMS:-72}"
    
    local job_id

    export SIMULATION_THREADS="$SIMULATION_THREADS"

    job_id=$(qsub \
        -terse \
        -pe smp $SIMULATION_THREADS \
        -q long \
        -t 1-${max_array_idx} \
        -tc ${max_concurrent} \
        -o "logs/$COORD_RUN_NAME/workflows/$WORKFLOW_NUMBER/simulations/\$JOB_NAME_\$JOB_ID_\$TASK_ID.out" \
        -e "logs/$COORD_RUN_NAME/workflows/$WORKFLOW_NUMBER/simulations/\$JOB_NAME_\$JOB_ID_\$TASK_ID.err" \
        "${WORK_DIR}/uge/simulation_uge.sh" "$params_dir" "$output_dir"
    )
    
    if [[ $? -eq 0 ]]; then
        JOB_IDS["simulation"]="$job_id"
        echo "workflow_$WORKFLOW_NUMBER,openfoam_array,submitted,$(date '+%s.%N')" >> "$STATUS_FILE"
        log_info "Submitted simulation array job: ${job_id}"
        log_info "  Array range: 1-${max_array_idx}"
        log_info "  Max concurrent: ${max_concurrent}"
    else
        log_error "Failed to submit simulation array job"
        return 1
    fi
}

################################################################################
# SSH Distribution (UCSB)
################################################################################

_run_simulations_ssh() {
    local params_file="$1"
    local output_dir="$2"
    local num_sims="$3"
    local cores="$4"
    
    # SSH configuration
    local ssh_opts="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -i ${SSH_KEY_PATH}"
    local remote_user="$(whoami)"
    local remote_work_dir="${UCSB_REMOTE_WORK_DIR:-$WORK_DIR}"
    local sim_run_id="$(date +%s)"
    
    # Parse machine list
    local machine_names=()
    local machine_ips=()
    while IFS=' ' read -r name ip; do
        [[ -z "$name" || "$name" =~ ^# ]] && continue
        machine_names+=("$name")
        machine_ips+=("$ip")
    done < "$MACHINE_LIST_FILE"
    
    if [[ ${#machine_ips[@]} -eq 0 ]]; then
        log_error "No machines in machine list"
        return 1
    fi
    
    log_info "=========================================="
    log_info "Machine Setup Phase"
    log_info "=========================================="
    log_info "SSH key verified: ${SSH_KEY_PATH}"
    log_info "Machines in list: ${#machine_ips[@]}"
    for i in "${!machine_ips[@]}"; do
        log_info "  ${machine_names[$i]}: ${machine_ips[$i]}"
    done
    
    ############################################################################
    # Test connectivity
    ############################################################################
    log_info "Testing machine connectivity..."
    local avail_names=()
    local avail_ips=()
    
    # Parallel connectivity test
    local conn_pids=()
    local conn_status=()
    for i in "${!machine_ips[@]}"; do
        (
            if ssh $ssh_opts "$remote_user@${machine_ips[$i]}" "echo test" &>/dev/null; then
                exit 0
            else
                exit 1
            fi
        ) &
        conn_pids+=($!)
    done
    
    for i in "${!conn_pids[@]}"; do
        if wait "${conn_pids[$i]}" 2>/dev/null; then
            log_info "✓ Machine accessible: ${machine_names[$i]} (${machine_ips[$i]})"
            avail_names+=("${machine_names[$i]}")
            avail_ips+=("${machine_ips[$i]}")
        else
            log_warn "✗ Machine NOT accessible: ${machine_names[$i]} (${machine_ips[$i]})"
        fi
    done
    
    local num_available=${#avail_ips[@]}
    if [[ $num_available -eq 0 ]]; then
        log_error "No machines are accessible!"
        return 1
    fi
    log_info "Available machines: $num_available"
    
    ############################################################################
    # Environment Deployment Phase
    ############################################################################
    log_info "=========================================="
    log_info "Environment Deployment Phase"
    log_info "=========================================="
    
    local deploy_script="${WORK_DIR}/tasks/deploy_to_machine.sh"
    local machines_to_remove=()
    
    if [[ -f "$deploy_script" ]]; then
        local deploy_tmpdir
        deploy_tmpdir=$(mktemp -d)
        local deploy_pids=()

        # Launch all deployments in parallel
        for i in "${!avail_ips[@]}"; do
            local machine="${avail_ips[$i]}"
            local mname="${avail_names[$i]}"
            log_info "Deploying environment to ${mname}..."
            (
                export REMOTE_WORK_DIR="$remote_work_dir"
                if bash "$deploy_script" "$machine" "$SSH_KEY_PATH" "$WORK_DIR" \
                        > "${deploy_tmpdir}/${i}.out" 2>&1; then
                    echo "ok" > "${deploy_tmpdir}/${i}.status"
                else
                    echo "fail" > "${deploy_tmpdir}/${i}.status"
                fi
            ) &
            deploy_pids+=($!)
        done

        # Wait for all and collect results
        for pid in "${deploy_pids[@]}"; do
            wait "$pid" 2>/dev/null || true
        done

        for i in "${!avail_ips[@]}"; do
            local mname="${avail_names[$i]}"
            local status_file="${deploy_tmpdir}/${i}.status"
            local out_file="${deploy_tmpdir}/${i}.out"
            sed 's/^/  /' "$out_file" 2>/dev/null
            if [[ "$(cat "$status_file" 2>/dev/null)" == "ok" ]]; then
                log_info "✓ Environment deployed successfully to ${mname}"
            else
                log_warn "✗ Deployment failed on ${mname} - removing from available list"
                machines_to_remove+=("$i")
            fi
        done
        rm -rf "$deploy_tmpdir"

        # Remove failed machines
        for idx in "${machines_to_remove[@]}"; do
            unset 'avail_ips[$idx]'
            unset 'avail_names[$idx]'
        done
        avail_ips=("${avail_ips[@]}")
        avail_names=("${avail_names[@]}")
        num_available=${#avail_ips[@]}
        
        if [[ $num_available -eq 0 ]]; then
            log_error "No machines available after deployment!"
            return 1
        fi
    else
        # Fallback: just sync simulation code
        log_info "No deploy script found, syncing simulation code only..."
        local sync_pids=()
        for machine in "${avail_ips[@]}"; do
            (
                timeout 60 ssh $ssh_opts "$remote_user@$machine" "mkdir -p '$remote_work_dir'" 2>/dev/null && \
                timeout 120 rsync -a --delete -q \
                    -e "ssh $ssh_opts" \
                    --exclude='.git' --exclude='__pycache__' --exclude='data' \
                    --exclude='models' --exclude='training' --exclude='*.ipynb' \
                    "${WORK_DIR}/simulation/" \
                    "$remote_user@$machine:$remote_work_dir/simulation/" 2>/dev/null
            ) &
            sync_pids+=($!)
        done
        for pid in "${sync_pids[@]}"; do
            wait "$pid" 2>/dev/null || true
        done
    fi
    
    log_info "Ready machines: $num_available"
    
    # Unzip template on each machine (quietly)
    log_info "Extracting simulation template on all machines..."
    local -a unzip_pids=()
    for machine in "${avail_ips[@]}"; do
        ssh $ssh_opts "$remote_user@$machine" "
            cd '$remote_work_dir/simulation' && \
            unzip -q -o cups_structure.zip >/dev/null 2>&1 || true
        " &
        unzip_pids+=($!)
    done
    for pid in "${unzip_pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
    log_info "Template extracted on ${num_available} machines"
    
    ############################################################################
    # Build simulation queue from params file
    ############################################################################
    local -a queue_ws=()
    local -a queue_wd=()
    local -a queue_idx=()
    local sim_count=0
    
    while IFS=',' read -r ws wd; do
        [[ "$ws" == "wind_speed" ]] && continue
        ws=$(echo "$ws" | xargs)
        wd=$(echo "$wd" | xargs)
        queue_ws+=("$ws")
        queue_wd+=("$wd")
        queue_idx+=("$sim_count")
        sim_count=$((sim_count + 1))
    done < "$params_file"
    
    ############################################################################
    # Simulation Execution Phase
    ############################################################################
    log_info "=========================================="
    log_info "Simulation Execution Phase"
    log_info "=========================================="
    
    # Show machine assignments
    for ((m=0; m<num_available; m++)); do
        local nsims_for_m=$(( (sim_count - m + num_available - 1) / num_available ))
        [[ $m -ge $sim_count ]] && nsims_for_m=0
        log_info "Machine $m (${avail_ips[$m]}): $nsims_for_m simulations"
    done
    
    # Dispatch all simulations round-robin
    local remote_sim_dir="$remote_work_dir/simulation/sim_runs_${sim_run_id}"
    local -a sim_machine=()
    local -a sim_machine_idx=()
    local -a sim_ws=()
    local -a sim_wd=()
    local -a sim_ux=()
    local -a sim_uy=()
    local -a sim_logfile=()
    
    for ((q=0; q<sim_count; q++)); do
        local m_idx=$((q % num_available))
        local machine="${avail_ips[$m_idx]}"
        local ws="${queue_ws[$q]}"
        local wd="${queue_wd[$q]}"
        local sim_idx="${queue_idx[$q]}"
        
        log_info "Dispatching: SIM $sim_idx to machine $m_idx (${machine}) - WS=$ws, WD=$wd"

        # Convert wind speed + direction to x/y components
        # x = north, y = east; wd = compass bearing wind blows towards (0=N, 90=E)
        local ux uy
        read ux uy < <(python3 "${WORK_DIR}/utils/wind_components.py" "${ws}" "${wd}")
        log_info "  Wind components: Ux=${ux} m/s, Uy=${uy} m/s"

        local logfile="${output_dir}/sim_${sim_idx}_ws_${ws}_wd_${wd}.log"

        # Run simulation on remote machine (background)
        ssh $ssh_opts "$remote_user@$machine" "
            source ~/.bashrc 2>/dev/null || true
            # Source OpenFOAM
            for of in /opt/openfoam11/etc/bashrc /opt/openfoam10/etc/bashrc; do
                [ -f \"\$of\" ] && source \"\$of\" && break
            done 2>/dev/null
            mkdir -p '$remote_sim_dir'
            cd '$remote_work_dir/simulation'
            bash runme.sh cups_structure.zip '$cores' '$ux' '$uy' '0' '$remote_sim_dir' '4' '$sim_idx' '$wd' 2>&1
        " > "$logfile" 2>&1 &
        
        sim_machine+=("$machine")
        sim_machine_idx+=("$m_idx")
        sim_ws+=("$ws")
        sim_wd+=("$wd")
        sim_ux+=("$ux")
        sim_uy+=("$uy")
        sim_logfile+=("$logfile")
    done
    
    log_info "Dispatched initial batch: $sim_count simulations"
    
    ############################################################################
    # Result Collection with Polling
    ############################################################################
    log_info "=========================================="
    log_info "Result Collection & Progress Tracking"
    log_info "=========================================="
    
    local completed=0
    local failed_count=0
    local -a failed_sims=()
    
    for ((q=0; q<sim_count; q++)); do
        local machine="${sim_machine[$q]}"
        local m_idx="${sim_machine_idx[$q]}"
        local ws="${sim_ws[$q]}"
        local wd="${sim_wd[$q]}"
        local ux="${sim_ux[$q]}"
        local uy="${sim_uy[$q]}"
        local sim_idx="${queue_idx[$q]}"
        # Use wind components (ux) not wind speed (ws) for naming - matches what runme.sh creates
        local sim_tag="sim_${sim_idx}_ws_${ux}_wd_${wd}"
        local expected_csv="${remote_sim_dir}/${sim_tag}.csv"
        
        log_info "[SIM $q] Waiting for completion on machine $m_idx (${machine})"
        log_info "[SIM $q] Polling for completion on $machine (expect: $expected_csv)"
        
        local poll_start=$(date +%s)
        local max_wait=2700  # 45 min (matches simulation_slurm.sh 40min limit + 5min buffer)
        local poll_interval=30
        local last_log_time=0
        local poll_count=0
        local sim_done=false
        
        while true; do
            local elapsed=$(( $(date +%s) - poll_start ))
            poll_count=$((poll_count + 1))
            
            # Check if the CSV result exists on remote
            if ssh $ssh_opts "$remote_user@$machine" "[ -f '$expected_csv' ]" 2>/dev/null; then
                log_info "[SIM $q] ✓ Completed on $machine (elapsed: ${elapsed}s, polls: $poll_count)"
                sim_done=true
                break
            fi
            
            # Check timeout
            if [[ $elapsed -ge $max_wait ]]; then
                log_error "[SIM $q] Timeout on $machine (${max_wait}s, $poll_count polls)"
                break
            fi
            
            # Log progress every 5 minutes
            if [[ $((elapsed - last_log_time)) -ge 300 ]]; then
                log_info "[SIM $q] Still running on $machine (elapsed: ${elapsed}s, polls: $poll_count)"
                ssh $ssh_opts "$remote_user@$machine" "ls -lh $remote_sim_dir 2>/dev/null | tail -3" 2>&1 \
                    | sed 's/^/[SIM '$q'] DEBUG: /' || true
                last_log_time=$elapsed
            fi
            
            sleep $poll_interval
        done
        
        if [[ "$sim_done" == "true" ]]; then
            # Copy results back
            log_info "Copying results from $machine..."
            if rsync -a \
                -e "ssh $ssh_opts" \
                "$remote_user@$machine:$remote_sim_dir/${sim_tag}.csv" \
                "$output_dir/" 2>/dev/null; then
                log_info "Results copied from $machine"
                log_info "[SIM $q] ✓ Results collected, machine $m_idx now free"
                completed=$((completed + 1))
            else
                log_warn "[SIM $q] ⚠ Results collection failed from $machine"
                failed_sims+=("$q")
                failed_count=$((failed_count + 1))
            fi
            
            # Cleanup remote processor directories to save disk
            ssh $ssh_opts "$remote_user@$machine" "
                cd '$remote_sim_dir' 2>/dev/null && rm -rf processor* 2>/dev/null || true
            " &
        else
            failed_sims+=("$q")
            failed_count=$((failed_count + 1))
        fi
    done
    
    ############################################################################
    # Final Verification
    ############################################################################
    log_info "=========================================="
    log_info "Final Verification"
    log_info "=========================================="
    
    local csv_count=$(ls -1 "$output_dir"/*.csv 2>/dev/null | wc -l)
    log_info "CSV files collected: $csv_count / $sim_count"
    
    if [[ ${#failed_sims[@]} -gt 0 ]]; then
        log_warn "Failed simulations: ${failed_sims[*]}"
    else
        log_info "All simulations completed successfully!"
    fi
    
    log_info "Results directory: $output_dir"
    while IFS= read -r line; do
        log_info "  $line"
    done < <(ls -lh "$output_dir"/*.csv 2>/dev/null | tail -5)

    log_info "Final status: ${completed}/${sim_count} completed, ${failed_count} failed"
    
    log_info "=========================================="
    log_info "Parallel simulation orchestration complete"
    log_info "=========================================="
}

################################################################################
# Local Sequential (Fallback)
################################################################################

_run_simulations_local() {
    local params_file="$1"
    local output_dir="$2"
    local num_sims="$3"
    local cores="$4"
    
    log_info "Running ${num_sims} simulations sequentially..."
    
    local sim_idx=0
    while IFS=',' read -r ws wd; do
        # Skip header
        [[ "$ws" == "wind_speed" ]] && continue
        
        ws=$(echo "$ws" | xargs)
        wd=$(echo "$wd" | xargs)
        
        log_info "[SIM ${sim_idx}] wind_speed=${ws}, wind_dir=${wd}"
        
        bash "${WORK_DIR}/tasks/simulation_task.sh" \
            "$ws" "$wd" "$output_dir" "$cores" "$sim_idx"
        
        sim_idx=$((sim_idx + 1))
    done < "$params_file"
    
    log_info "Completed ${sim_idx} simulations"
}

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

################################################################################
# Simulation Results
################################################################################

count_simulation_results() {
    local output_dir="$1"
    count_files "$output_dir" "*.csv"
}

validate_simulation_results() {
    local output_dir="$1"
    local expected_count="$2"
    
    local actual_count=$(count_simulation_results "$output_dir")
    
    if [[ $actual_count -eq $expected_count ]]; then
        log_info "Simulation results: ${actual_count}/${expected_count} (complete)"
        return 0
    else
        log_warn "Simulation results: ${actual_count}/${expected_count} (incomplete)"
        return 1
    fi
}
