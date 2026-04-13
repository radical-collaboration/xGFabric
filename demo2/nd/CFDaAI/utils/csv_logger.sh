#!/usr/bin/env bash

# ---------------------------------------------------------------------------
# csv_logger.sh
# Safe CSV logging with exclusive file locking via flock(1).
# ---------------------------------------------------------------------------

# Resolve the lock file descriptor once at the top level so it can be
# reused across multiple calls without re-opening on every invocation.
readonly CSV_LOCK_FD=200

# ---------------------------------------------------------------------------
# log_workflow_update
#
# Usage:
#   log_workflow_update <workflow_id> <task> <status> <status_file>
#
# Appends one CSV row to <status_file> under an exclusive flock lock.
# Creates the file (with a header) if it does not already exist.
# ---------------------------------------------------------------------------
log_workflow_update() {
    local workflow_id="${1:?workflow_id is required}"
    local task="${2:?task is required}"
    local status="${3:?status is required}"
    local status_file="${4:?status_file is required}"

    # Use printf for the timestamp — $() strips trailing newlines,
    # and date's %N gives nanoseconds (GNU coreutils).
    local timestamp
    timestamp=$(date '+%s.%N')

    # Sanitise fields: strip embedded commas and double-quotes so the
    # resulting row is always valid single-line CSV.
    local safe_workflow_id safe_task safe_status
    safe_workflow_id=$(printf '%s' "${workflow_id}" | tr -d ',"')
    safe_task=$(printf '%s'        "${task}"        | tr -d ',"')
    safe_status=$(printf '%s'      "${status}"      | tr -d ',"')

    local lock_file="${status_file}.lock"

    # Open (or create) the lock file on a fixed fd, then flock it.
    # Using a dedicated fd avoids spawning a subshell for every call,
    # which is measurably faster under high concurrency.
    (
        # Subshell isolates the fd and the lock — it is released
        # automatically when the subshell exits.
        exec 200>"${lock_file}" || {
            printf 'ERROR: cannot open lock file %s\n' "${lock_file}" >&2
            exit 1  # exit subshell, not return
        }

        flock --exclusive --wait 10 200 || {
            printf 'ERROR: could not acquire lock on %s within 10 s\n' \
                "${lock_file}" >&2
            exit 1
        }

        # Write header on first use.
        if [[ ! -s "${status_file}" ]]; then
            printf 'workflow_id,task,status,timestamp\n' >> "${status_file}"
        fi

        printf '%s,%s,%s,%s\n' \
            "${safe_workflow_id}" \
            "${safe_task}"        \
            "${safe_status}"      \
            "${timestamp}"        >> "${status_file}"
    ) || return 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    log_workflow_update "$@"
fi