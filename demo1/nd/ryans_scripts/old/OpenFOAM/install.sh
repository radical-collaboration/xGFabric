#!/bin/bash

# activate conda environment
source ~/.bashrc
conda activate cctools-env

# add OpenFOAM module to computer
module add openfoam/10.0/gcc/8.5.0
module add paraview/5.11.2

# check if the directory exists
DIRECTORY=openfoam-partial

if [ -d "$DIRECTORY" ]; then
    cd openfoam-partial
    echo "$DIRECTORY already existed. restoring all"
    foamCleanTutorials
else 
    echo "Downloading repo..."
    git clone --no-checkout https://develop.openfoam.com/committees/hpc openfoam-partial
    cd openfoam-partial
    git sparse-checkout init --cone
    git sparse-checkout set combustion/reactingFoam/LES/DLRCJH
    git checkout master
fi

cd ..