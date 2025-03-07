#!/bin/bash

# rm -rf "./temp/squarecil"

# activate conda environment
conda init
conda activate cctools-env

# add OpenFOAM module to computer
module add openfoam/10.0/gcc/8.5.0
module add paraview/5.11.2

# get test file from OpenFOAM website
mkdir "temp"
cd "./temp"

wget http://www.wolfdynamics.com/wiki/squarecil.tar.gz
# sh run_solver.sh
echo "paraFoam -builtin" >> run_solver.sh

# run solver
sh run_solver.sh