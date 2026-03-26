#!/bin/bash
#
# dispatch.sh - Unified task dispatcher
#
# Handles task execution across different environments:
# - NERSC: submit via SLURM
# - UCSB with machines: distribute via SSH
# - UCSB local: direct execution
#
# Usage:
#   source lib/dispatch.sh
#   dispatch_task <task_type> [depends_on] [args...]

# Track submitted job IDs for dependency chaining
declare -A JOB_IDS=()

################################################################################
# Main Dispatcher
################################################################################

dispatch_task() {
    local task_type="$1"
    local depends_on="${2:-}"  # Comma-separated list of task types to wait for
    shift 2 2>/dev/null || shift 1 2>/dev/null || true
    local task_args=("$@")
    
    local task_script="${WORK_DIR}/tasks/${task_type}.sh"
    local slurm_script="${WORK_DIR}/slurm/${task_type}_slurm.sh"
    local uge_script="${WORK_DIR}/uge/${task_type}_uge.sh"
    
    log_info "Dispatching task: ${task_type}"
    
    # Determine execution mode
    if [[ "$SYSTEM_TYPE" == "nersc" ]] && [[ -f "$slurm_script" ]]; then
        _dispatch_slurm "$task_type" "$depends_on" "$slurm_script" "${task_args[@]}"

    elif [[ "$HAS_MACHINE_LIST" == "true" ]] && _task_supports_ssh "$task_type"; then
        _dispatch_ssh "$task_type" "$task_script" "${task_args[@]}"

    elif [[ "$SYSTEM_TYPE" == "nd" ]] && [[ -f "$uge_script" ]]; then
        _dispatch_uge "$task_type" "$depends_on" "$uge_script" "${task_args[@]}"

    else
        _dispatch_local "$task_type" "$task_script" "${task_args[@]}"
    fi
}

################################################################################
# SLURM Dispatch (NERSC)
################################################################################

_dispatch_slurm() {
    local task_type="$1"
    local depends_on="$2"
    local slurm_script="$3"
    shift 3
    local task_args=("$@")
    
    # Build dependency string
    local dep_string=""
    if [[ -n "$depends_on" ]]; then
        local dep_jobs=()
        IFS=',' read -ra deps <<< "$depends_on"
        for dep in "${deps[@]}"; do
            if [[ -n "${JOB_IDS[$dep]:-}" ]]; then
                dep_jobs+=("${JOB_IDS[$dep]}")
            fi
        done
        if [[ ${#dep_jobs[@]} -gt 0 ]]; then
            dep_string="--dependency=afterok:$(IFS=:; echo "${dep_jobs[*]}")"
        fi
    fi
    
    # Prepare arguments for export
    local args_string="${task_args[*]}"
    
    # Submit SLURM job
    local job_id
    job_id=$(sbatch --parsable $dep_string \
             --export=ALL,TASK_TYPE="${task_type}",TASK_ARGS="${args_string}" \
             "$slurm_script" 2>&1)
    
    if [[ $? -eq 0 ]] && [[ "$job_id" =~ ^[0-9]+$ ]]; then
        JOB_IDS["$task_type"]="$job_id"
        log_info "Submitted ${task_type} as SLURM job ${job_id}"
        echo "$job_id"
    else
        log_error "Failed to submit SLURM job for ${task_type}: ${job_id}"
        return 1
    fi
}

################################################################################
# UGE Dispatch (ND)
################################################################################

_dispatch_uge() {
    local task_type="$1"
    local depends_on="$2"
    local uge_script="$3"
    shift 3
    local task_args=("$@")

    # Build dependency string
    local dep_string=""
    if [[ -n "$depends_on" ]]; then
        local dep_jobs=()
        IFS=',' read -ra deps <<< "$depends_on"
        for dep in "${deps[@]}"; do
            if [[ -n "${JOB_IDS[$dep]:-}" ]]; then
                dep_jobs+=("${JOB_IDS[$dep]}")
            fi
        done
        if [[ ${#dep_jobs[@]} -gt 0 ]]; then
            dep_string="-hold_jid $(IFS=,; echo "${dep_jobs[*]}")"
        fi
    fi

    # Prepare arguments for export
    local args_string="${task_args[*]}"

    # Submit UGE job
    local job_id
    job_id=$(qsub -terse $dep_string \
             -V -v TASK_TYPE="${task_type}",TASK_ARGS="${args_string}" \
             "$uge_script" 2>&1)

    # -terse guarantees purely numeric output on success
    if [[ $? -eq 0 ]] && [[ "$job_id" =~ ^[0-9]+$ ]]; then
        JOB_IDS["$task_type"]="$job_id"
        log_info "Submitted ${task_type} as UGE job ${job_id}"
        echo "$job_id"
    else
        log_error "Failed to submit UGE job for ${task_type}: ${job_id}"
        return 1
    fi
}


################################################################################
# SSH Dispatch (UCSB with machine list)
################################################################################

_dispatch_ssh() {
    local task_type="$1"
    local task_script="$2"
    shift 2
    local task_args=("$@")
    
    log_info "Dispatching ${task_type} via SSH to ${MACHINE_COUNT} machines..."
    
    # Task-specific SSH distribution scripts
    case "$task_type" in
        simulation)
            bash "${WORK_DIR}/lib/simulations.sh" ssh "${task_args[@]}"
            ;;
        pcr_train)
            bash "${WORK_DIR}/training/pcr/train_pcr_distributed.sh" "${task_args[@]}"
            ;;
        *)
            # Generic: run on first available machine
            log_warn "No SSH distribution logic for ${task_type}, running locally"
            _dispatch_local "$task_type" "$task_script" "${task_args[@]}"
            ;;
    esac
}

################################################################################
# Local Dispatch
################################################################################

_dispatch_local() {
    local task_type="$1"
    local task_script="$2"
    shift 2
    local task_args=("$@")
    
    log_info "Running ${task_type} locally..."
    
    if [[ -f "$task_script" ]]; then
        bash "$task_script" "${task_args[@]}"
    else
        log_error "Task script not found: ${task_script}"
        return 1
    fi
}

################################################################################
# Task Support Checks
################################################################################

_task_supports_ssh() {
    local task_type="$1"
    
    # Tasks that can be distributed via SSH
    case "$task_type" in
        simulation|pcr_train)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

################################################################################
# Wait for Tasks
################################################################################

wait_for_tasks() {
    local tasks="${1:-}"  # Comma-separated list, or empty for all
    
    if [[ "$SYSTEM_TYPE" == "nersc" ]]; then
        _wait_slurm_jobs "$tasks"
    elif [ "$SYSTEM_TYPE" == "nd" ]; then
        _wait_uge_jobs "$tasks"
    else
        # Local execution: wait for tracked background processes
        # (bare 'wait' would also block on RAM monitor)
        log_info "Local mode: background tasks managed by polling"
    fi
}

_wait_slurm_jobs() {
    local tasks="$1"
    
    local jobs_to_wait=()
    
    if [[ -n "$tasks" ]]; then
        IFS=',' read -ra task_list <<< "$tasks"
        for task in "${task_list[@]}"; do
            if [[ -n "${JOB_IDS[$task]:-}" ]]; then
                jobs_to_wait+=("$task:${JOB_IDS[$task]}")
            fi
        done
    else
        for task in "${!JOB_IDS[@]}"; do
            jobs_to_wait+=("$task:${JOB_IDS[$task]}")
        done
    fi
    
    for job_info in "${jobs_to_wait[@]}"; do
        local task="${job_info%:*}"
        local job_id="${job_info#*:}"
        
        log_info "Waiting for ${task} (job ${job_id})..."
        
        # Track wait time
        local wait_start=$(date +%s.%N)
        local queue_time=0
        local run_time=0
        
        # Get job submission info
        local submit_time=$(sacct -j "$job_id" --format=Submit --noheader 2>/dev/null | head -1 | xargs)
        local start_time=$(sacct -j "$job_id" --format=Start --noheader 2>/dev/null | head -1 | xargs)
        
        while squeue -j "$job_id" &>/dev/null 2>&1; do
            sleep 30
        done
        
        local wait_end=$(date +%s.%N)
        local total_wait=$(echo "$wait_end - $wait_start" | bc)
        
        # Check exit status and timing via sacct
        local status
        local elapsed
        status=$(sacct -j "$job_id" --format=State --noheader | head -1 | xargs)
        elapsed=$(sacct -j "$job_id" --format=Elapsed --noheader 2>/dev/null | head -1 | xargs)
        
        log_info "[LATENCY] ${task} (job ${job_id}): waited ${total_wait}s for completion"
        log_info "[LATENCY] ${task} execution time: ${elapsed}"
        
        if [[ -n "${LATENCY_LOG:-}" ]]; then
            echo "${task}_wait: ${total_wait}s" >> "${LATENCY_LOG}"
            echo "${task}_exec: ${elapsed}" >> "${LATENCY_LOG}"
        fi
        
        if [[ "$status" == "COMPLETED" ]]; then
            log_info "${task} (job ${job_id}) completed successfully"
        else
            log_warn "${task} (job ${job_id}) ended with status: ${status}"
        fi
    done
}

_wait_uge_jobs() {
    local tasks="$1"
    local jobs_to_wait=()
    
    if [[ -n "$tasks" ]]; then
        IFS=',' read -ra task_list <<< "$tasks"
        for task in "${task_list[@]}"; do
            if [[ -n "${JOB_IDS[$task]:-}" ]]; then
                jobs_to_wait+=("$task:${JOB_IDS[$task]}")
            fi
        done
    else
        for task in "${!JOB_IDS[@]}"; do
            jobs_to_wait+=("$task:${JOB_IDS[$task]}")
        done
    fi

    for job_info in "${jobs_to_wait[@]}"; do
        local task="${job_info%:*}"
        local job_id="${job_info#*:}"
        
        log_info "Waiting for ${task} (job ${job_id})..."
        
        # Track wait time
        local wait_start=$(date +%s)
        
        # Wait while job is still in queue or running
        while qstat -j "$job_id" &>/dev/null 2>&1; do
            # now=$(date +%s)
            # printf "[TIMER] Training for %d seconds\n" "$((now - wait_start))"
            sleep 10
        done
        
        local wait_end=$(date +%s.%N)
        local total_wait=$(echo "$wait_end - $wait_start" | bc)
        
        log_info "[LATENCY] ${task} (job ${job_id}): waited ${total_wait}s for completion"
    done
}

################################################################################
# Job Management
################################################################################

get_job_id() {
    local task_type="$1"
    echo "${JOB_IDS[$task_type]:-}"
}

cancel_task() {
    local task_type="$1"
    local job_id="${JOB_IDS[$task_type]:-}"
    
    if [[ -n "$job_id" ]]; then
        log_info "Cancelling ${task_type} (job ${job_id})..."
        scancel "$job_id" 2>/dev/null || qdel "$job_id" 2>/dev/null || true
        unset JOB_IDS["$task_type"]
    fi
}

cancel_all_tasks() {
    for task in "${!JOB_IDS[@]}"; do
        cancel_task "$task"
    done
}
