#!/bin/bash
source ~/.bashrc
module --force purge

# Check if Conda is installed
if ! command -v conda &> /dev/null; then
    echo "Conda is not installed or not in PATH."
    echo "Installing Conda..."
    mkdir -p ~/miniconda3
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
    bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
    rm ~/miniconda3/miniconda.sh
    source ~/miniconda3/bin/activate
    conda init bash
    source ~/.bashrc
fi

if ! conda --help &> /dev/null; then
    echo "Conda is available but failed to run (permission error or runtime failure)."
    exit 1
fi

# Check wheter the xGFabric conda environment has been created
if ! conda env list | grep -q "xgfabric"; then
    echo "creating fabric environment"
    conda env create -f environment.yml
fi

# Check if CSPOT is installed
if ! which senspot-get &> /dev/null; then
    echo "CSPOT is not installed or not in PATH. Installing..."
    sh cspot_install.sh
fi