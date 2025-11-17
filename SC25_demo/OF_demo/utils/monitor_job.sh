#!/bin/bash

################################################################################
# Job Monitoring Helper
#
# Monitors a submitted job until completion
# Usage: ./monitor_job.sh <job_id> <case_directory>
################################################################################

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <job_id> <case_directory>"
    exit 1
fi

JOB_ID="$1"
CASE_DIR="$2"

if [ ! -d "$CASE_DIR" ]; then
    echo "Error: Case directory not found: $CASE_DIR"
    exit 1
fi

CHECK_INTERVAL=10  # seconds between status checks
MAX_WAIT=86400     # 24 hours maximum wait time

log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_info "Monitoring job $JOB_ID..."

ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    # Check if job still exists in queue
    if qstat -j "$JOB_ID" > /dev/null 2>&1; then
        # Job is still running
        STATE=$(qstat -j "$JOB_ID" 2>/dev/null | grep "job_state" | awk '{print $NF}')
        log_info "Job $JOB_ID state: $STATE"
    else
        # Job completed or doesn't exist
        log_info "Job $JOB_ID completed"
        
        # Check if simulation log exists and contains success indicator
        if [ -f "$CASE_DIR/log" ]; then
            if grep -q "End" "$CASE_DIR/log"; then
                log_info "Simulation completed successfully"
                exit 0
            else
                log_info "Simulation may have encountered errors. Check $CASE_DIR/log"
                exit 1
            fi
        else
            log_info "No simulation log found at $CASE_DIR/log"
            exit 1
        fi
    fi
    
    sleep $CHECK_INTERVAL
    ELAPSED=$((ELAPSED + CHECK_INTERVAL))
done

echo "ERROR: Job monitoring timed out after $MAX_WAIT seconds"
exit 1

EOF
