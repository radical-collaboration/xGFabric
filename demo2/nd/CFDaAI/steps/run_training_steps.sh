#!/bin/bash
#
# run_training_steps.sh - Run in-the-loop pipeline for each step in training_steps.csv
#
# For each pending step:
#   1. Patches config.sh: DATA_CUTOFF_DATE, CSPOT_LIMIT, HISTORICAL_DATA_PATH
#   2. Runs main.sh (full pipeline: simulations + training, all archived together)
#   3. Parses [ARCHIVE] line from main.sh output to get the archive path
#   4. Writes archive_path + status=done back to training_steps.csv
#
# Usage:
#   bash run_training_steps.sh [OPTIONS]
#
# Options:
#   --steps-file PATH        Path to training_steps.csv  (default: steps/training_steps.csv)
#   --models "pcr pinn fno"  Models to train (default: pcr pinn fno)
#   --system TYPE            System type: hybrid, ucsb, nersc (default: hybrid)
#   --start-step N           Start from step number N (default: 1)
#   --max-steps N            Stop after N steps (default: run all pending)
#   --dry-run                Print what would be done but do not execute
#
# Example:
#   bash steps/run_training_steps.sh --models "pcr pinn fno" --max-steps 5
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(dirname "$SCRIPT_DIR")"

################################################################################
# Defaults
################################################################################

STEPS_FILE="${SCRIPT_DIR}/training_steps.csv"
MODELS="pcr pinn fno"
SYSTEM_TYPE="hybrid"
START_STEP=1
MAX_STEPS=999999
DRY_RUN=false
HISTORICAL_DATA_PATH="/local/home/liubov_kurafeeva/storage/cups_historical"

################################################################################
# Argument parsing
################################################################################

while [[ $# -gt 0 ]]; do
    case "$1" in
        --steps-file)  STEPS_FILE="$2";     shift 2 ;;
        --models)      MODELS="$2";         shift 2 ;;
        --system)      SYSTEM_TYPE="$2";    shift 2 ;;
        --start-step)  START_STEP="$2";     shift 2 ;;
        --max-steps)   MAX_STEPS="$2";      shift 2 ;;
        --dry-run)     DRY_RUN=true;        shift   ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ ! -f "$STEPS_FILE" ]]; then
    echo "ERROR: steps file not found: $STEPS_FILE"
    echo "Run: python3 steps/generate_training_steps.py"
    exit 1
fi


################################################################################
# Helpers
################################################################################

log()  { echo "[run_steps] $(date '+%H:%M:%S') $*"; }
err()  { echo "[run_steps] ERROR: $*" >&2; }

# Read the CSV into parallel arrays (pure bash, no awk dependency)
# Returns: STEP_IDS, START_DATES, CUTOFF_DATES, N_RECORDS, STATUSES, ARCHIVE_PATHS
declare -a STEP_IDS START_DATES CUTOFF_DATES N_RECORDS_ARR STATUSES ARCHIVE_PATHS

load_steps() {
    STEP_IDS=(); START_DATES=(); CUTOFF_DATES=()
    N_RECORDS_ARR=(); STATUSES=(); ARCHIVE_PATHS=()
    local first=1
    while IFS=',' read -r step_id start_date cutoff_date n_records status archive_path; do
        if [[ $first -eq 1 ]]; then first=0; continue; fi  # skip header
        STEP_IDS+=("$step_id")
        START_DATES+=("$start_date")
        CUTOFF_DATES+=("$cutoff_date")
        N_RECORDS_ARR+=("$n_records")
        STATUSES+=("$status")
        ARCHIVE_PATHS+=("$archive_path")
    done < "$STEPS_FILE"
}

# Rewrite steps file from current arrays.
# Re-reads the file first so that any external edits (e.g. skip-no-wu) made
# while the script is running are preserved — only the in-memory status and
# archive_path for the current step overwrite the on-disk value.
save_steps() {
    local tmpfile="${STEPS_FILE}.tmp"
    echo "step_id,start_date,cutoff_date,n_records,status,archive_path" > "$tmpfile"
    # Build lookup from in-memory arrays (step_id -> status,archive)
    declare -A _mem_status _mem_archive
    for idx in "${!STEP_IDS[@]}"; do
        _mem_status["${STEP_IDS[$idx]}"]="${STATUSES[$idx]}"
        _mem_archive["${STEP_IDS[$idx]}"]="${ARCHIVE_PATHS[$idx]}"
    done
    # Re-read on-disk file; for each row use in-memory status/archive
    local first=1
    while IFS=',' read -r sid sdate cdate nrec sstatus sarchive; do
        if [[ $first -eq 1 ]]; then first=0; continue; fi
        local use_status="${_mem_status[$sid]:-$sstatus}"
        local use_archive="${_mem_archive[$sid]:-$sarchive}"
        echo "${sid},${sdate},${cdate},${nrec},${use_status},${use_archive}"
    done < "$STEPS_FILE" >> "$tmpfile"
    mv "$tmpfile" "$STEPS_FILE"
}

# Patch a KEY=VALUE line in config.sh (handles quoted and unquoted values)
patch_config() {
    local key="$1" value="$2"
    local cfg="${WORK_DIR}/config.sh"
    if grep -q "^${key}=" "$cfg"; then
        sed -i "s|^${key}=.*|${key}=\"${value}\"|" "$cfg"
    else
        # Key doesn't exist — append it
        echo "${key}=\"${value}\"" >> "$cfg"
    fi
}

# Uncomment or set a KEY=VALUE line (handles commented-out lines like # KEY=...)
upsert_config() {
    local key="$1" value="$2"
    local cfg="${WORK_DIR}/config.sh"
    # Remove any existing commented or uncommented version of this key
    sed -i "/^[[:space:]]*#*[[:space:]]*${key}=/d" "$cfg"
    # Append clean version
    echo "${key}=\"${value}\"" >> "$cfg"
}

################################################################################
# Main loop
################################################################################

log "Starting training steps runner"
log "  Steps file : $STEPS_FILE"
log "  Models     : $MODELS"
log "  System     : $SYSTEM_TYPE"
log "  Start step : $START_STEP"
log "  Max steps  : $MAX_STEPS"
log "  Dry run    : $DRY_RUN"

load_steps

total_steps=${#STEP_IDS[@]}
log "Loaded ${total_steps} steps from CSV"

run_count=0

for idx in "${!STEP_IDS[@]}"; do
    step_id="${STEP_IDS[$idx]}"
    step_num="${step_id#0}"  # strip leading zeros for numeric compare
    status="${STATUSES[$idx]}"
    cutoff="${CUTOFF_DATES[$idx]}"
    start="${START_DATES[$idx]}"

    # Skip steps before start-step
    if [[ "$step_num" -lt "$START_STEP" ]]; then
        continue
    fi

    # Stop after max-steps completed this session
    if [[ "$run_count" -ge "$MAX_STEPS" ]]; then
        log "Reached --max-steps $MAX_STEPS, stopping."
        break
    fi

    # Skip non-pending steps
    if [[ "$status" != "pending" ]]; then
        log "Step ${step_id}: status=${status}, skipping"
        continue
    fi

    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Step ${step_id} / ${total_steps}  cutoff=${cutoff}  start=${start}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "  [dry-run] Would patch config and run main.sh"
        continue
    fi

    # ── 1. Patch config.sh ──────────────────────────────────────────────────
    log "  Patching config.sh: DATA_CUTOFF_DATE=${cutoff}, CSPOT_LIMIT=72"
    patch_config "DATA_CUTOFF_DATE" "$cutoff"
    patch_config "CSPOT_LIMIT" "72"
    upsert_config "HISTORICAL_DATA_PATH" "$HISTORICAL_DATA_PATH"

    # Mark step as running so a crash leaves a clear marker
    STATUSES[$idx]="running"
    save_steps

    # ── 2. Clear previous simulation data so training uses only this step's sims ──
    SIM_DIR="${WORK_DIR}/results/iteration_1/simulations"
    if [[ -d "$SIM_DIR" ]]; then
        log "  Clearing old simulation data: ${SIM_DIR}"
        find "${SIM_DIR}" -mindepth 1 -delete
    fi

    # ── 3. Run main.sh ───────────────────────────────────────────────────────
    LOG_FILE="${SCRIPT_DIR}/logs/step_${step_id}.log"
    mkdir -p "${SCRIPT_DIR}/logs"

    log "  Running main.sh — log: ${LOG_FILE}"
    set +e
    "${WORK_DIR}/main.sh" \
        --system "$SYSTEM_TYPE" \
        --mode full \
        --iterations 1 \
        --models "$MODELS" \
        2>&1 | tee "$LOG_FILE"
    EXIT_CODE=$?
    set -e

    # ── 4. Parse [ARCHIVE] line ──────────────────────────────────────────────
    ARCHIVE_PATH=""
    if grep -q "\[ARCHIVE\]" "$LOG_FILE"; then
        ARCHIVE_PATH=$(grep "\[ARCHIVE\].*Done:" "$LOG_FILE" | tail -1 | sed 's/.*\[ARCHIVE\][[:space:]]*Done:[[:space:]]*//')
        log "  Archive path: ${ARCHIVE_PATH}"
    else
        log "  WARNING: no [ARCHIVE] line found in log"
    fi

    # ── 5. Update steps CSV ──────────────────────────────────────────────────
    if [[ $EXIT_CODE -eq 0 ]]; then
        STATUSES[$idx]="done"
        ARCHIVE_PATHS[$idx]="$ARCHIVE_PATH"
        log "  Step ${step_id} done ✓"
    else
        STATUSES[$idx]="error"
        ARCHIVE_PATHS[$idx]="exit_code=${EXIT_CODE}"
        err "Step ${step_id} failed with exit code ${EXIT_CODE}"
    fi
    save_steps

    # ── 6. Dedup archives to free disk space ─────────────────────────────────
    log "  Running dedup_archives.py to free duplicate simulation files..."
    python3 "${WORK_DIR}/../dedup_archives.py" 2>&1 | tail -4 | while read -r line; do log "  [dedup] $line"; done

    run_count=$((run_count + 1))
done

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Session complete. Ran ${run_count} step(s)."
log "Steps file updated: ${STEPS_FILE}"
