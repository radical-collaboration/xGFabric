#!/bin/bash
# activate environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate cfdaai
num_cores=32

if [ "$(hostname -f | grep nersc.gov)" ]; then
    work_queue_factory -w 72 -W 72 -T slurm --cores=$num_cores -B "--qos=regular --constraint=cpu --time=02:00:00 --cpus-per-task=${num_cores}" -N xgfabric -d all
elif [ "$(hostname -f | grep nd.edu)" ]; then
    work_queue_factory -w 72 -W 72 -T condor --cores $num_cores -N xgfabric -d all
fi
