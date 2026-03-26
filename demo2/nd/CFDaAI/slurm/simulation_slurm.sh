#!/bin/bash
#SBATCH --job-name=cfd_sim_array
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=32
#SBATCH --time=00:40:00
#SBATCH --output=/global/homes/k/kurl/jobs_logs/%x_%A_%a.out
#SBATCH --error=/global/homes/k/kurl/jobs_logs/%x_%A_%a.err
#
# simulation_slurm.sh - SLURM job array for CFD simulations
#
# Submit as:
#   sbatch --array=0-N slurm/simulation_slurm.sh <param_dir> <output_dir>
#
# Where N = number of simulations - 1

set -euo pipefail

################################################################################
# Configuration
################################################################################

# Use WORK_DIR from environment if available, otherwise derive from script location
if [[ -z "${WORK_DIR:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    WORK_DIR="$(dirname "$SCRIPT_DIR")"
fi

# Arguments
PARAM_DIR="${1:-${WORK_DIR}/params}"
OUTPUT_DIR="${2:-${WORK_DIR}/results}"

# SLURM array index
TASK_ID="${SLURM_ARRAY_TASK_ID:-0}"

################################################################################
# Get Parameter File
################################################################################

# Find parameter file for this task ID
PARAM_FILES=("${PARAM_DIR}"/sim_*.json)

if [[ ! -f "${PARAM_FILES[0]}" ]]; then
    echo "ERROR: No parameter files found in: ${PARAM_DIR}"
    exit 1
fi

# Get the file for this array index
PARAM_FILE="${PARAM_FILES[$TASK_ID]}"

if [[ ! -f "$PARAM_FILE" ]]; then
    echo "ERROR: Parameter file not found for task ${TASK_ID}"
    exit 1
fi

echo "Task ${TASK_ID}: Processing ${PARAM_FILE}"

################################################################################
# Execute Simulation Task
################################################################################

exec "${WORK_DIR}/tasks/simulation_task.sh" "$PARAM_FILE" "$OUTPUT_DIR"
