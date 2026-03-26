#!/bin/bash
#$ -N cfd_sim_array
#$ -V
#$ -o jobs_logs/$JOB_NAME_$JOB_ID_$TASK_ID.out
#$ -e jobs_logs/$JOB_NAME_$JOB_ID_$TASK_ID.err
#
# simulation_uge.sh - UGE job array for CFD simulations
#
# Submit as:
#   qsub --array=1-N uge/simulation_uge.sh <param_dir> <output_dir>
#
# Where N = number of simulations - 1

set -euo pipefail

################################################################################
# Configuration
################################################################################

params_dir="$1"
OUTPUT_DIR="$2"

# UGE array index
TASK_ID="${SGE_TASK_ID:-1}"

if [ "$TASK_ID" == "1" ]; then
    echo "Job $JOB_NUMBER: running" >> "$COORD_LOG_FILE"
fi

################################################################################
# Get Parameter File
################################################################################

# Find parameter file for this task ID
# Get the file for this array index
PARAM_FILE="${params_dir}/sim_${TASK_ID}.json"

if [[ ! -f "$PARAM_FILE" ]]; then
    echo "ERROR: Parameter file not found for task ${TASK_ID}"
    exit 1
fi

echo "Task ${TASK_ID}: Processing ${PARAM_FILE}"

################################################################################
# Execute Simulation Task
################################################################################

exec "tasks/simulation_task.sh" "$PARAM_FILE" "$OUTPUT_DIR"
