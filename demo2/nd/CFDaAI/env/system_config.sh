#!/bin/bash
#
# system_config.sh - System detection and configuration
#
# Usage: source this file to detect and configure the execution environment
#
# Exports:
#   SYSTEM_TYPE     - "nersc", "ucsb", or "hybrid"
#   SCRIPT_DIR      - Directory containing this script
#   WORK_DIR        - Working directory for the intheloop system
#   OPENFOAM_ROOT   - OpenFOAM installation path
#   SCRATCH_DIR     - Scratch/working directory for data
#   ARCHIVE_BASE    - Archive directory for results
#   HAS_SLURM       - "true" if SLURM scheduler available
#   HAS_CSPOT       - "true" if CSPOT available
#   HAS_GPU         - "true" if GPU available
#   HAS_MACHINE_LIST - "true" if SSH machine list available
#   MACHINE_COUNT   - Number of machines in machine_list.txt

set -e

# Determine script directory
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
fi
export WORK_DIR="$(dirname "$SCRIPT_DIR")"


################################################################################
# System Detection
################################################################################

detect_system() {
    # Respect SYSTEM_TYPE if already set (e.g., via --system flag)
    if [[ -n "${SYSTEM_TYPE:-}" ]]; then
        case "${SYSTEM_TYPE}" in
            nersc|ucsb|local|hybrid|nd)
                log_info "Using forced SYSTEM_TYPE=${SYSTEM_TYPE}"
                ;;
            *)
                log_warn "Unknown SYSTEM_TYPE=${SYSTEM_TYPE}, auto-detecting"
                unset SYSTEM_TYPE
                ;;
        esac
    fi

    if [[ -z "${SYSTEM_TYPE:-}" ]]; then
        # Auto-detect: check for NERSC indicators.
        # NOTE: Only check NERSC_HOST if set by the system (NERSC sets it on login
        # nodes). In hybrid mode from UCSB, config.sh uses NERSC_SSH_HOST instead,
        # so NERSC_HOST is not present and won't trigger a false NERSC detection.
        if [[ -n "${NERSC_HOST:-}" ]] || \
           [[ -f "/etc/nersc" ]] || \
           [[ -d "/global/common/software" && "$(hostname)" =~ nid|login ]]; then
            export SYSTEM_TYPE="nersc"
        elif [ "$(hostname | grep nd)" ]; then
            export SYSTEM_TYPE="nd"
        else
            export SYSTEM_TYPE="ucsb"
        fi
    fi

    # Set system-specific path defaults
    case "${SYSTEM_TYPE}" in
        nersc)
            export OPENFOAM_ROOT="${OPENFOAM_ROOT:-/global/common/software/m5290/openfoam}"
            export SCRATCH_DIR="${PSCRATCH:-/pscratch/sd/${USER:0:1}/${USER}}"
            export ARCHIVE_BASE="${SCRATCH_DIR}/experiment_archive"
            ;;
        nd)
            export OPENFOAM_ROOT="${OPENFOAM_ROOT:-/software/o/openfoam/10.0-mpich/OpenFOAM-10}"
            export MPI_ROOT="${MPI_ROOT:-/opt/crc/o/openmpi/5.0.5/gcc/11.4.1/}"
            export SCRATCH_DIR="${SCRATCH_DIR:-/scratch/foam/cases}"
            export ARCHIVE_BASE="${ARCHIVE_BASE:-/scratch/foam/cases/archived}"
            ;;
        hybrid|ucsb|local)
            export OPENFOAM_ROOT="${OPENFOAM_ROOT:-/opt/openfoam11}"
            export SCRATCH_DIR="${SCRATCH_DIR:-/sims/cases}"
            export ARCHIVE_BASE="${ARCHIVE_BASE:-/sims/cases/archived}"
            ;;
    esac

    log_info "Detected system: ${SYSTEM_TYPE}"
}

################################################################################
# Feature Detection
################################################################################

detect_features() {
    # find scheduler
    if command -v sbatch &>/dev/null; then
        export SCHEDULER="SLURM"
    elif command -v qstat &>/dev/null; then
        export SCHEDULER="UGE"
    else
        export SCHEDULER="None"
    fi

    # CSPOT data system
    # Check standard paths and NERSC-specific locations
    local nersc_cspot="/global/common/software/m5290/cspot/build/bin"
    local user_cspot="$HOME/common/cspot/build/bin"  # User's own CSPOT build
    local user_bin="$HOME/bin"
    if command -v senspot-get &>/dev/null; then
        export HAS_CSPOT="true"
    elif [[ -x "${user_cspot}/senspot-get" ]]; then
        # User's common/cspot build (NERSC)
        export HAS_CSPOT="true"
        export PATH="${user_cspot}:$PATH"
        log_info "Using CSPOT from: ${user_cspot}"
    elif [[ -x "${user_bin}/senspot-get" ]]; then
        # User's bin directory (UCSB default)
        export HAS_CSPOT="true"
        export PATH="${user_bin}:$PATH"
        log_info "Using CSPOT from: ${user_bin}"
    elif [[ -x "${nersc_cspot}/senspot-get" ]]; then
        export HAS_CSPOT="true"
        export PATH="${nersc_cspot}:$PATH"
        log_info "Using CSPOT from: ${nersc_cspot}"
    else
        # Don't use mock senspot-get from utils/
        export HAS_CSPOT="false"
    fi
    
    # GPU availability
    if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]] || command -v nvidia-smi &>/dev/null 2>&1; then
        export HAS_GPU="true"
    else
        export HAS_GPU="false"
    fi
    
    log_info "Features: Scheduler=${SCHEDULER}, CSPOT=${HAS_CSPOT}, GPU=${HAS_GPU}"
}

################################################################################
# Machine List Detection (for SSH-based distribution)
################################################################################

check_machine_list() {
    local machine_list="${WORK_DIR}/machine_list.txt"
    local ssh_key="${WORK_DIR}/id_rsa"
    
    if [[ -f "$machine_list" ]] && [[ -f "$ssh_key" ]]; then
        export HAS_MACHINE_LIST="true"
        export MACHINE_COUNT=$(grep -v '^#' "$machine_list" | grep -v '^$' | wc -l)
        export MACHINE_LIST_FILE="$machine_list"
        export SSH_KEY_PATH="$ssh_key"
        log_info "Machine list: ${MACHINE_COUNT} machines available"
    else
        export HAS_MACHINE_LIST="false"
        export MACHINE_COUNT=0
        log_info "Machine list: not available (local execution only)"
    fi
}

################################################################################
# NERSC Connectivity and Hybrid Mode Helpers
################################################################################

# check_nersc_connectivity
# Returns 0 if NERSC is reachable via SSH, 1 otherwise.
check_nersc_connectivity() {
    local key="${NERSC_SSH_KEY:-${WORK_DIR}/id_rsa}"
    local user="${NERSC_USER:-kurl}"
    local host="${NERSC_SSH_HOST:-perlmutter.nersc.gov}"

    if [[ ! -f "$key" ]]; then
        log_error "NERSC SSH key not found: ${key}"
        return 1
    fi

    ssh -q -i "$key" \
        -o ConnectTimeout=10 \
        -o BatchMode=yes \
        -o StrictHostKeyChecking=no \
        "${user}@${host}" "echo ok" &>/dev/null
}

# get_module_system <module>
# Returns "ucsb", "nersc", or "racelab" for the given module based on HYBRID_MODULE_<MODULE>.
# Falls back to "ucsb" if not set.
get_module_system() {
    local module="$1"
    local var="HYBRID_MODULE_${module^^}"
    echo "${!var:-ucsb}"
}

# check_racelab_connectivity
# Returns 0 if racelab-gpu1 is reachable via SSH, 1 otherwise.
check_racelab_connectivity() {
    local key="${RACELAB_SSH_KEY:-${WORK_DIR}/racelabgpu}"
    local user="${RACELAB_USER:-liubov_kurafeeva}"
    local host="${RACELAB_SSH_HOST:-rw-gpu1.cs.ucsb.edu}"

    if [[ ! -f "$key" ]]; then
        log_error "Racelab SSH key not found: ${key}"
        return 1
    fi

    ssh -q -i "$key" \
        -o ConnectTimeout=10 \
        -o BatchMode=yes \
        -o StrictHostKeyChecking=no \
        "${user}@${host}" "echo ok" &>/dev/null
}

# validate_hybrid_nersc
# Called at pipeline start when SYSTEM_TYPE=hybrid.
# Fails fast if any module is assigned to a remote machine that is not reachable.
validate_hybrid_nersc() {
    local needs_nersc=false
    local needs_racelab=false
    for module in DATA SIMULATIONS PCR PINN FNO; do
        local var="HYBRID_MODULE_${module}"
        case "${!var:-ucsb}" in
            nersc)   needs_nersc=true ;;
            racelab) needs_racelab=true ;;
        esac
    done

    local rc=0

    if [[ "$needs_nersc" == "true" ]]; then
        log_info "Hybrid mode: checking NERSC connectivity to ${NERSC_SSH_HOST:-perlmutter.nersc.gov}..."
        if ! check_nersc_connectivity; then
            log_error "NERSC is not accessible but required modules are assigned to NERSC"
            for module in DATA SIMULATIONS PCR PINN FNO; do
                local var="HYBRID_MODULE_${module}"
                if [[ "${!var:-ucsb}" == "nersc" ]]; then
                    log_error "  HYBRID_MODULE_${module}=nersc"
                fi
            done
            log_error "SSH key: ${NERSC_SSH_KEY:-${WORK_DIR}/id_rsa}"
            log_error "Host:    ${NERSC_SSH_HOST:-perlmutter.nersc.gov}"
            rc=1
        else
            log_info "NERSC connectivity: OK"
        fi
    else
        log_info "Hybrid mode: no modules assigned to NERSC, skipping NERSC check"
    fi

    if [[ "$needs_racelab" == "true" ]]; then
        log_info "Hybrid mode: checking racelab connectivity to ${RACELAB_SSH_HOST:-rw-gpu1.cs.ucsb.edu}..."
        if ! check_racelab_connectivity; then
            log_error "racelab-gpu1 is not accessible but required modules are assigned to it"
            for module in DATA SIMULATIONS PCR PINN FNO; do
                local var="HYBRID_MODULE_${module}"
                if [[ "${!var:-ucsb}" == "racelab" ]]; then
                    log_error "  HYBRID_MODULE_${module}=racelab"
                fi
            done
            log_error "SSH key: ${RACELAB_SSH_KEY:-${WORK_DIR}/racelabgpu}"
            log_error "Host:    ${RACELAB_SSH_HOST:-rw-gpu1.cs.ucsb.edu}"
            log_error "Run env/setup_racelab.sh if this is the first time using racelab"
            rc=1
        else
            log_info "Racelab connectivity: OK"
        fi
    else
        log_info "Hybrid mode: no modules assigned to racelab, skipping racelab check"
    fi

    return $rc
}

################################################################################
# Environment Loading
################################################################################

load_environment() {
    local env_script="${WORK_DIR}/env/env_${SYSTEM_TYPE}.sh"

    if [[ -f "$env_script" ]]; then
        log_info "Loading environment: ${env_script}"
        source "$env_script"
    else
        log_error "Environment script not found: ${env_script}"
        return 1
    fi

    # In hybrid mode, also load racelab env if any module routes there
    if [[ "${SYSTEM_TYPE}" == "hybrid" ]]; then
        local needs_racelab=false
        for module in DATA SIMULATIONS PCR PINN FNO; do
            local var="HYBRID_MODULE_${module}"
            if [[ "${!var:-ucsb}" == "racelab" ]]; then
                needs_racelab=true
                break
            fi
        done
        if [[ "$needs_racelab" == "true" ]]; then
            local racelab_env="${WORK_DIR}/env/env_racelab.sh"
            if [[ -f "$racelab_env" ]]; then
                source "$racelab_env"
            else
                log_warn "env_racelab.sh not found but modules are routed to racelab"
            fi
        fi
    fi
}

################################################################################
# Initialization
################################################################################

init_system() {
    # Source common utilities first (for log_* functions)
    if [[ -f "${WORK_DIR}/lib/common.sh" ]]; then
        source "${WORK_DIR}/lib/common.sh"
    else
        # Minimal logging if common.sh not yet available
        log_info()  { echo "[INFO]  $(date '+%H:%M:%S') $1"; }
        log_warn()  { echo "[WARN]  $(date '+%H:%M:%S') $1"; }
        log_error() { echo "[ERROR] $(date '+%H:%M:%S') $1" >&2; }
    fi
    
    detect_system
    detect_features
    check_machine_list
    load_environment
    
    # Source grid configuration
    if [[ -f "${WORK_DIR}/training/pcr/read_grid_config.sh" ]]; then
        source "${WORK_DIR}/training/pcr/read_grid_config.sh"
    fi
    
    log_info "System initialization complete"
}
