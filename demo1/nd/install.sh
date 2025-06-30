#!/bin/bash
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
fi

# Try to run conda with --help or similar to avoid side effects
if conda --help &> /dev/null; then
    echo "Conda is available and works for the current user."
else
    echo "Conda is available but failed to run (permission error or runtime failure)."
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


# Try to run senspot-get or similar to avoid side effects
if which senspot-get &> /dev/null; then
    echo "CSPOT is available and works for the current user."
    exit 0
else
    echo "CSPOT is not installed or not in PATH."
    echo -n "Where would you like CSPOT to be installed?

==> The default location is \$HOME/.cspot. Leave blank for default.
==> "

    read location
    HERE=`pwd`
    if [ -z "$location" ]; then
        echo "Installing CSPOT to $HOME/.cspot"
        cd cspot
        sh install.sh $option
    else
        echo "Installing CSPOT to $location ..."
        cd cspot
        sh install.sh $option $location
    fi
    source ~/.bashrc
    cd $HERE
fi
