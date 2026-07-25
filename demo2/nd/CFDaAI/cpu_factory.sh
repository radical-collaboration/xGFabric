#!/bin/bash
# activate environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate cfdaai
num_cores=64
num_workers=72
mem=$((1024 * 30))
disk=$((1024 * 30))

if [ "$(hostname -f | grep nersc.gov)" ]; then
    work_queue_factory --min-workers=$num_workers --max-workers=$num_workers -T slurm --cores=$num_cores -B "--qos=regular --constraint=cpu --time=02:00:00 --cpus-per-task=${num_cores}" -N xgfabric -d all
elif [ "$(hostname -f | grep nd.edu)" ]; then
    work_queue_factory --min-workers=$num_workers --max-workers=$num_workers --timeout=86400 --factory-timeout=86400 -T condor --cores $num_cores --memory=$mem --disk=$disk -N xgfabric -d all
    # work_queue_factory -w 72 -W 72 -T condor --cores $num_cores -N xgfabric -d all
fi
