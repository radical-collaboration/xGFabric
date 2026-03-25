#!/bin/bash
WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_DIR="${WORK_DIR}/utils"

# setup the environment
source $UTILS_DIR/env_setup.sh

# make sure that these folders exist
mkdir -p "logs"
mkdir -p "scripts"

# activate environment
conda activate xgfabric

# launch the coordinator
python3 $UTILS_DIR/coordinator.py
