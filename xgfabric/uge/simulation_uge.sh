#!/bin/bash
#
# simulation_uge.sh - UGE job array for CFD simulations

set -euo pipefail

################################################################################
# Configuration
################################################################################

params_dir="$1"
OUTPUT_DIR="$2"
TASK_ID="$3"

################################################################################
# Get Parameter File
################################################################################

# Find parameter file for this task ID
PARAM_FILE="${params_dir}/sim_${TASK_ID}.json"

if [[ ! -f "$PARAM_FILE" ]]; then
    echo "ERROR: Parameter file not found for task ${TASK_ID}"
    exit 1
fi

echo "Task ${TASK_ID}: Processing ${PARAM_FILE}"

################################################################################
# Execute Simulation Task
################################################################################

bash "tasks/simulation_task.sh" "$PARAM_FILE" "$OUTPUT_DIR"

echo "Task ${TASK_ID}: Finished processing ${PARAM_FILE}"
