#!/bin/bash

# activate conda environment
source ~/.bashrc
conda activate cctools-env

# add OpenFOAM module to computer
module add openfoam/10.0/gcc/8.5.0
module add paraview/5.11.2

# reset examples and figures from prior runs.
rm -rf damBreak
rm -rf figures

cp -r $FOAM_TUTORIALS/multiphase/interFoam/laminar/damBreak/damBreak .
mkdir figures
