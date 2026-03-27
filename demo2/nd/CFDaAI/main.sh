#!/bin/bash
WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_DIR="${WORK_DIR}/utils"
ENV_DIR="${WORK_DIR}/env"

# setup the environment
source $ENV_DIR/env_coordinator.sh

# activate environment
conda activate xgfabric

# launch the coordinator
python3 $UTILS_DIR/coordinator.py
