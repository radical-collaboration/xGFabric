#!/bin/bash
if conda env list | grep -q "nd-xgfabric"
then
    echo "already created fabric environment"
else
    echo "creating fabric environment"
    conda env create -f ../environment.yml
fi

conda activate nd-xgfabric

mkdir data
# Function to run woofc-namespace-platform in an infinite loop inside "data" directory
run_woofc() {
    cd data || { echo "Directory 'data' not found!"; exit 1; }
    while true; do
        woofc-namespace-platform -b spawn
        sleep 1  # Optional delay to avoid hammering
    done
}

# Function to run replicate-unl-data.sh every 3 minutes
run_replicator() {
    while true; do
        sh replicate-unl-data.sh
        sleep 20  # 3 minutes
    done
}

# Start the replicator in the background
run_replicator &

# Start woofc in the foreground (inside data/)
run_woofc
