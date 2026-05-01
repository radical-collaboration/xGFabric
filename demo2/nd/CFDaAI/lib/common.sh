#!/bin/bash
#
# common.sh - Shared utility functions
#
# Source this file for logging, timing, and common operations

################################################################################
# Logging Functions
################################################################################

log_info() {
    echo "[INFO] $(date '+%H:%M:%S') $1" >&2
}

log_warn() {
    echo "[WARN] $(date '+%H:%M:%S') $1" >&2
}

log_error() {
    echo "[ERROR] $(date '+%H:%M:%S') $1" >&2
}

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo "[DEBUG] $(date '+%H:%M:%S') $1" >&2
    fi
}

log_section() {
    local title="$1"
    echo "" >&2
    echo "[INFO] $(date '+%H:%M:%S') ==========================================" >&2
    echo "[INFO] $(date '+%H:%M:%S') $title" >&2
    echo "[INFO] $(date '+%H:%M:%S') ==========================================" >&2
}

log_subsection() {
    local title="$1"
    echo "[INFO] $(date '+%H:%M:%S') --- $title ---" >&2
}

################################################################################
# Timing Utilities
################################################################################

declare -A _START_TIMES
declare -A _SECTION_DURATIONS
_SCRIPT_START_TIME=""

timer_start() {
    local section="${1:-main}"
    _START_TIMES["$section"]=$(date +%s)
    if [[ -z "$_SCRIPT_START_TIME" ]]; then
        _SCRIPT_START_TIME=$(date +%s)
    fi
}

timer_end() {
    local section="${1:-main}"
    local end_time=$(date +%s)
    local start_time=${_START_TIMES["$section"]:-$end_time}
    local duration=$((end_time - start_time))
    _SECTION_DURATIONS["$section"]=$duration
    
    log_info "[TIMER] ${section}: $(format_duration $duration)"
    return 0
}

format_duration() {
    local duration=$1
    local hours=$((duration / 3600))
    local minutes=$(((duration % 3600) / 60))
    local seconds=$((duration % 60))
    
    if [[ $duration -ge 3600 ]]; then
        echo "${hours}h ${minutes}m ${seconds}s"
    elif [[ $duration -ge 60 ]]; then
        echo "${minutes}m ${seconds}s"
    else
        echo "${duration}s"
    fi
}

print_timing_summary() {
    log_info "========== TIMING SUMMARY =========="
    for section in "${!_SECTION_DURATIONS[@]}"; do
        local dur=${_SECTION_DURATIONS[$section]}
        log_info "  $(printf '%-30s' "$section:") $(format_duration $dur)"
    done
    
    if [[ -n "$_SCRIPT_START_TIME" ]]; then
        local total=$(($(date +%s) - _SCRIPT_START_TIME))
        log_info "  $(printf '%-30s' "TOTAL:") $(format_duration $total)"
    fi
    log_info "===================================="
}

################################################################################
# Memory & Disk Utilities
################################################################################

get_available_memory_gb() {
    free -g 2>/dev/null | awk '/^Mem:/{print $7}' || echo "0"
}

get_available_disk_gb() {
    local path="${1:-$WORK_DIR}"
    df -BG "$path" 2>/dev/null | awk 'NR==2 {print $4}' | sed 's/G//' || echo "0"
}

check_memory() {
    local required_gb="${1:-20}"
    local available=$(get_available_memory_gb)
    
    if [[ $available -lt $required_gb ]]; then
        log_error "Insufficient memory: ${available}GB < ${required_gb}GB required"
        return 1
    fi
    log_info "Memory check passed: ${available}GB available"
    return 0
}

check_disk_space() {
    local required_gb="${1:-20}"
    local path="${2:-$WORK_DIR}"
    local available=$(get_available_disk_gb "$path")
    
    if [[ $available -lt $required_gb ]]; then
        log_error "Insufficient disk space: ${available}GB < ${required_gb}GB required"
        return 1
    fi
    log_info "Disk space check passed: ${available}GB available"
    return 0
}

################################################################################
# File Operations
################################################################################

ensure_dir() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        log_debug "Created directory: $dir"
    fi
}

safe_copy() {
    local src="$1"
    local dst="$2"
    
    if [[ -f "$src" ]]; then
        cp "$src" "$dst"
        return 0
    else
        log_warn "Source file not found: $src"
        return 1
    fi
}

count_files() {
    local dir="$1"
    local pattern="${2:-*}"
    find "$dir" -maxdepth 1 -name "$pattern" -type f 2>/dev/null | wc -l
}

################################################################################
# Process Management
################################################################################

wait_for_pid() {
    local pid=$1
    local name="${2:-process}"
    local timeout="${3:-0}"  # 0 = no timeout
    local start_time=$(date +%s)
    
    while kill -0 "$pid" 2>/dev/null; do
        if [[ $timeout -gt 0 ]]; then
            local elapsed=$(($(date +%s) - start_time))
            if [[ $elapsed -ge $timeout ]]; then
                log_error "Timeout waiting for ${name} (PID: $pid)"
                return 1
            fi
        fi
        sleep 5
    done
    
    wait "$pid"
    return $?
}

kill_process_tree() {
    local pid=$1
    local children=$(pgrep -P "$pid" 2>/dev/null)
    
    for child in $children; do
        kill_process_tree "$child"
    done
    
    kill "$pid" 2>/dev/null || true
}

################################################################################
# Validation
################################################################################

require_file() {
    local file="$1"
    local description="${2:-Required file}"
    
    if [[ ! -f "$file" ]]; then
        log_error "${description} not found: ${file}"
        return 1
    fi
    return 0
}

require_dir() {
    local dir="$1"
    local description="${2:-Required directory}"
    
    if [[ ! -d "$dir" ]]; then
        log_error "${description} not found: ${dir}"
        return 1
    fi
    return 0
}

require_command() {
    local cmd="$1"
    local description="${2:-Required command}"
    
    if ! command -v "$cmd" &>/dev/null; then
        log_error "${description} not available: ${cmd}"
        return 1
    fi
    return 0
}

################################################################################
# System Metrics Collection
################################################################################

COLLECT_METRICS=${COLLECT_METRICS:-false}

# Get current memory usage in MB
get_memory_usage_mb() {
    free -m 2>/dev/null | awk '/^Mem:/{print $3}' || echo "0"
}

################################################################################
# Results Archiving
################################################################################

# Archive the results directory into ARCHIVE_BASE with a descriptive folder name.
# Folder name format: experiment_<short_info>_<YYYYMMDD_HHMMSS>
# After successful copy the source results directory is removed.
#
# Args: results_dir  short_info_label
archive_results() {
    local results_dir="$1"
    local short_info="${2:-run}"
    local archive_base="${ARCHIVE_DIR:-${ARCHIVE_BASE:-}}"

    if [[ -z "$archive_base" ]]; then
        log_warn "[ARCHIVE] ARCHIVE_BASE not set — skipping archive"
        return 0
    fi

    if [[ ! -d "$results_dir" ]]; then
        log_warn "[ARCHIVE] Results directory not found: ${results_dir}"
        return 0
    fi

    # Sanitise label: replace spaces/slashes with underscores, lowercase
    local label
    label=$(echo "$short_info" | tr ' /' '_' | tr '[:upper:]' '[:lower:]')
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local archive_name="experiment_${label}_${timestamp}"
    local archive_dest="${archive_base}/${archive_name}"

    log_info "[ARCHIVE] Archiving results → ${archive_dest}"
    mkdir -p "$archive_base"

    if cp -r "$results_dir" "$archive_dest"; then
        log_info "[ARCHIVE] Copy complete — removing source: ${results_dir}"
        rm -rf "$results_dir"
        log_info "[ARCHIVE] Done: ${archive_dest}"
    else
        log_warn "[ARCHIVE] Copy failed — source kept at: ${results_dir}"
        return 1
    fi
}

# Get number of CPU cores
get_cpu_cores() {
    nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo "0"
}

# Get total memory in MB
get_total_memory_mb() {
    free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo "0"
}

# Get available memory in MB
get_available_memory_mb() {
    free -m 2>/dev/null | awk '/^Mem:/{print $7}' || echo "0"
}

################################################################################
# RAM Monitoring (background sampler)
################################################################################

_RAM_MONITOR_PID=""
_RAM_MONITOR_FILE=""

# Start RAM monitoring for a section
# Usage: start_ram_monitor <section_name> [interval_seconds]
start_ram_monitor() {
    local section="$1"
    local interval="${2:-2}"
    
    _RAM_MONITOR_FILE=$(mktemp "/tmp/ram_monitor_${section}_XXXXXX.csv")
    
    # Write CSV header
    echo "timestamp,used_mb,available_mb,total_mb" > "$_RAM_MONITOR_FILE"
    
    (
        while true; do
            local line
            line=$(free -m | awk '/^Mem:/{printf "%d,%d,%d,%d", systime(), $3, $7, $2}')
            echo "$line" >> "$_RAM_MONITOR_FILE"
            sleep "$interval"
        done
    ) &
    _RAM_MONITOR_PID=$!
    
    log_info "RAM monitoring started (PID: $_RAM_MONITOR_PID, sampling every ${interval}s)"
}

# Stop RAM monitoring and report stats
# Usage: stop_ram_monitor <section_name>
stop_ram_monitor() {
    local section="$1"
    
    if [[ -n "$_RAM_MONITOR_PID" ]]; then
        kill "$_RAM_MONITOR_PID" 2>/dev/null || true
        wait "$_RAM_MONITOR_PID" 2>/dev/null || true
    fi
    
    if [[ -n "$_RAM_MONITOR_FILE" && -f "$_RAM_MONITOR_FILE" ]]; then
        local samples=$(tail -n +2 "$_RAM_MONITOR_FILE" | wc -l)
        
        if [[ $samples -gt 0 ]]; then
            local stats
            stats=$(awk -F',' 'NR>1 {
                if ($2 > peak) peak=$2;
                sum+=$2; count++;
                if (NR==2) start=$2;
                last=$2;
                avail=$3
            } END {
                avg=int(sum/count);
                delta=last-start;
                printf "%d %d %d %d %d", peak, avg, delta, avail, count
            }' "$_RAM_MONITOR_FILE")
            
            local peak=$(echo "$stats" | cut -d' ' -f1)
            local avg=$(echo "$stats" | cut -d' ' -f2)
            local delta=$(echo "$stats" | cut -d' ' -f3)
            local avail=$(echo "$stats" | cut -d' ' -f4)
            local count=$(echo "$stats" | cut -d' ' -f5)
            
            log_info "[RAM] ${section}: peak=${peak}MB avg=${avg}MB delta=${delta}MB avail=${avail}MB ($count samples)"
        fi
        
        rm -f "$_RAM_MONITOR_FILE"
    fi
    
    _RAM_MONITOR_PID=""
    _RAM_MONITOR_FILE=""
}

################################################################################
# Enhanced Timing Summary (flat format matching reference log)
################################################################################

# Print timing breakdown in the flat format:
#   [INFO] HH:MM:SS [TIMER] Section breakdown:
#   [INFO] HH:MM:SS   Environment Setup:             11s
#   [INFO] HH:MM:SS   OpenFOAM Simulations:          28m 56s
print_timing_breakdown() {
    log_info "[TIMER] Section breakdown:"
    
    for section in "${!_SECTION_DURATIONS[@]}"; do
        local dur=${_SECTION_DURATIONS[$section]}
        local formatted=$(format_duration $dur)
        log_info "$(printf '  %-30s %s' "${section}:" "$formatted")"
    done
    
    if [[ -n "$_SCRIPT_START_TIME" ]]; then
        local total=$(($(date +%s) - _SCRIPT_START_TIME))
        log_info "[TIMER] Total: $(format_duration $total)"
    fi
    
    # Print latency summary if available
    if [[ -n "${LATENCY_LOG:-}" && -f "$LATENCY_LOG" ]]; then
        log_info "[LATENCY] Job latency summary:"
        while IFS= read -r line; do
            [[ -n "$line" ]] && log_info "  $line"
        done < "$LATENCY_LOG"
    fi
}

# Export metrics to JSON  
export_metrics_json() {
    local output_file="$1"
    local total_duration=$(($(date +%s) - ${_SCRIPT_START_TIME:-$(date +%s)}))
    
    {
        echo "{"
        echo "  \"timestamp\": \"$(date -Iseconds)\","
        echo "  \"total_duration_seconds\": $total_duration,"
        echo "  \"system\": {"
        echo "    \"hostname\": \"$(hostname)\","
        echo "    \"cpu_cores\": $(get_cpu_cores),"
        echo "    \"memory_total_mb\": $(get_total_memory_mb)"
        echo "  },"
        echo "  \"sections\": {"
        
        local first=true
        for section in "${!_SECTION_DURATIONS[@]}"; do
            [[ "$first" == "false" ]] && echo ","
            first=false
            local dur=${_SECTION_DURATIONS[$section]}
            local json_section=$(echo "$section" | tr ' ()' '_' | tr -d '-')
            echo -n "    \"$json_section\": {\"duration_seconds\": $dur}"
        done
        
        echo ""
        echo "  }"
        echo "}"
    } > "$output_file"
    
    log_info "Metrics exported to: $output_file"
}
