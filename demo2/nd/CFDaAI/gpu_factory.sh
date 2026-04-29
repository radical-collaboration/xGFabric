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
    nersc_group=$(groups | awk -F" " '{print $2}')
    work_queue_factory -w 5 -T slurm -B "--constraint=gpu -G 1 -A ${nersc_group} --ntasks=${num_cores} --qos=regular" -N xgfabric
elif [ "$(hostname -f | grep nd.edu)" ]; then
    work_queue_factory -w 2 -T uge -B "-pe smp ${num_cores} -q gpu -l gpu_card=1" -N xgfabric
fi
