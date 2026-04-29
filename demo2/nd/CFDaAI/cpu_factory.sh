#!/bin/bash
WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_DIR="${WORK_DIR}/utils"
ENV_DIR="${WORK_DIR}/env"

# setup the environment
source $ENV_DIR/env_coordinator.sh

# activate environment
conda activate cfdaai

num_cores=32

if [ "$(hostname -f | grep nersc.gov)" ]; then
    work_queue_factory -w 5 -T slurm --cores=$num_cores -B "--qos=regular --constraint=cpu --nodes=1 --ntasks=1 --cpus-per-task=32" -N xgfabric
elif [ "$(hostname -f | grep nd.edu)" ]; then
    work_queue_factory -w 10 -T uge -B "-pe smp ${num_cores}" -N xgfabric
fi
