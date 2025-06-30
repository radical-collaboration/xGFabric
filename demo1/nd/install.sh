#!/bin/bash
source ~/.bashrc

echo -n "This script has been tested on the following clusters:
1. Purdue ANVIL
2. Notre Dame
3. Texas Stampede3

==> Which cluster are you running on? (1-3)
==> "

read option

if [ "$option" -eq 1 ]; then
    echo "==> You selected: Purdue ANVIL"
elif [ "$option" -eq 2 ]; then
    echo "==> You selected: Notre Dame"
elif [ "$option" -eq 3 ]; then
    echo "==> You selected: Texas Stampede3"
else
    echo "Invalid selection. Please choose 1, 2, or 3."
    exit 1
fi

echo "Checking if Conda is installed..."

# Check if Conda is installed
if ! command -v conda &> /dev/null; then
    echo "Conda is not installed or not in PATH."
    echo "Installing Conda..."
    mkdir -p ~/miniconda3
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
    bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
    rm ~/miniconda3/miniconda.sh
    conda init bash
    source ~/.bashrc
fi

if conda --help &> /dev/null; then
    echo "Conda is available and works for the current user."
else
    echo "Conda is available but failed to run (permission error or runtime failure)."
    exit 1
fi

echo "Checking if the xGFabric Conda environment is installed..."

# Check wheter the xGFabric conda environment has been created
if conda env list | grep -q "xgfabric"
then
    echo "xGFabric conda environment has already been installed"
else
    echo "creating fabric environment"
    conda env create -f environment.yml
fi

echo "Checking if the CSPOT is installed..."

# Check if CSPOT is installed
if which senspot-get &> /dev/null; then
    echo "CSPOT is available and works for the current user."
else
    echo "CSPOT is not installed or not in PATH. Installing..."
    sh cspot/install.sh
fi

# Install is completed
echo "All modules are installed correctly!"