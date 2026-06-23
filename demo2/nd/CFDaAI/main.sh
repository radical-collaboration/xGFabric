#!/bin/bash
source ~/miniconda3/etc/profile.d/conda.sh

WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_DIR="${WORK_DIR}/utils"
ENV_DIR="${WORK_DIR}/env"

# setup the environment
source $ENV_DIR/env_coordinator.sh

# activate environment
conda activate cfdaai

# launch the coordinator
python3 $UTILS_DIR/coordinator.py
