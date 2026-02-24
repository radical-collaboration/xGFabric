#!/bin/bash
source ~/.bashrc
module --force purge

echo "Checking if Conda is installed..."
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
    sh cspot_install.sh
fi

# Install is completed
echo "All modules are installed correctly!"

# check for display environment before rendering
if [ -z "$DISPLAY" ]; then
    printf "No X11 environment detected (DISPLAY is not set). If you are accessing the machine via SSH, then please reconnect with the -Y flag to pass your display variables.\n\nEX: ssh -Y user@machine.edu\n"
    exit 1
fi

if [ ! -f "$HOME/.cspot/capabilities.yaml" ] ||  [ ! -d "$HOME/.cspot" ]; then
    printf "Could not find the capabilities.yaml file in $HOME/.cspot. This file is required by CSPOT to authenticate data transfer from the UCSB cluster. If you have access to the capabilities.yaml file then please do the following:\n\n1. Create a folder named \".cspot\" in your home directory ($HOME/).\n2. Create or copy over the \"capabilities.yaml\" file and place it in the .cspot folder.\n3. Run chmod 700 on the \".cspot\" folder.\n4. Run chmod 600 on the \"capabilities.yaml\" file.\n\n\nIf you do not have access a capabilities.yaml file, then please contact Rich Wolski at rich@cs.ucsb.edu or visit his website at https://sites.cs.ucsb.edu/~rich/\n"
    exit 1
fi