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
    sh cspot/install.sh
fi

# Install is completed
echo "All modules are installed correctly!"

# prompt user if they would like to run a test simulation
printf "==> Would you like to run a test simulation of OpenFOAM? (y/[n])\n==> "
read simulation

lowercase="${simulation,,}"
case "$lowercase" in
    y | yes)
        if [ ! -f "$HOME/.cspot/capabilities.yaml" ] ||  [ ! -d "$HOME/.cspot" ]; then
            printf "Could not find the capabilities.yaml file in $HOME/.cspot. This file is required by CSPOT to authenticate data transfer from the UCSB cluster. If you have access to the capabilities.yaml file then please do the following:\n\n1. Create a folder named \".cspot\" in your home directory ($HOME/).\n2. Create or copy over the \"capabilities.yaml\" file and place it in the .cspot folder.\n3. Run chmod 700 on the \".cspot\" folder.\n4. Run chmod 600 on the \"capabilities.yaml\" file.\n\n\nIf you do not have access a capabilities.yaml file, then please contact Rich Wolski at rich@cs.ucsb.edu or visit his website at https://sites.cs.ucsb.edu/~rich/\n"
            exit 1
        fi

        printf "This script has been tested on the following clusters:\n1. Purdue ANVIL\n2. Notre Dame\n3. Texas Stampede3\n\n==> Which cluster are you running on? (1-3)\n==> "

        read option

        cd "OpenFOAM/parallel_test/"

        if [ "$option" -eq 1 ]; then
            echo "==> You selected: Purdue ANVIL"
            sh runme.sh 1 5 3
        elif [ "$option" -eq 2 ]; then
            echo "==> You selected: Notre Dame"
            sh runme.sh 2 5 3
        elif [ "$option" -eq 3 ]; then
            echo "==> You selected: Texas Stampede3"
            sh runme.sh 3 5 3
        else
            echo "Invalid selection. Please choose 1, 2, or 3."
            exit 1
        fi
        ;;
    n | no | "")
        exit 0
        ;;
    *)
        echo "Invalid selection. Please enter either yes or no."
        exit 1
        ;;
esac

echo "Successfully ran the OpenFoam job."