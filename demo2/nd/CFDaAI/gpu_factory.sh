#!/bin/bash
# activate environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate cfdaai
num_cores=32

if [ "$(hostname -f | grep nersc.gov)" ]; then
    nersc_group=$(groups | awk -F" " '{print $2}')
    work_queue_factory -w 2 -T slurm -B "--constraint=gpu -G 1 -A ${nersc_group} --time=00:30:00 --ntasks=${num_cores} --qos=regular" -M xgfabric -d all
elif [ "$(hostname -f | grep nd.edu)" ]; then
    work_queue_factory -w 2 -W 4 -T uge -B "-pe smp ${num_cores} -q gpu -l gpu_card=1" -N xgfabric -d all
fi
