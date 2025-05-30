#!/bin/bash
#$ -v DISPLAY


########################$ -q long
######################$ -pe mpi-64 64
##########$ -pe mpi-48 48
#$ -v DISPLAY

module load openfoam/10.0/gcc/8.5.0 # For ND cluster
#source /opt/openfoam10/etc/bashrc # For UCSB pseudo cluster
module load paraview/5.11.2
module load conda

source ~/.bashrc

if conda env list | grep -q "nd-xgfabric"
then
    echo "already created fabric environment"
else
    echo "creating fabric environment"
    conda env create -f environment.yml
fi
conda init zsh
conda activate nd-xgfabric

destination="$1"

if [ -z "$DISPLAY" ]; then
    echo "No X11 environment detected (DISPLAY is not set). Exiting..."
else
    echo "X11 environment detected (DISPLAY=$DISPLAY). Generating images..."
    pvpython --force-offscreen-rendering render_foam.py $destination
fi


python3 create_gif.py "$destination"


echo "All done"
