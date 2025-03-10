#!/bin/bash

source ./foaminstall.sh

cd "./squarecil/RANS"

# add lines to solver script
echo "mpirun -np 4 simpleFoam -postProcess -func Q -parallel" >> run_solver.sh
echo "mpirun -np 4 simpleFoam -postProcess -func yPlus -parallel" >> run_solver.sh

echo "reconstructPar" >> run_solver.sh
echo "paraFoam -builtin" >> run_solver.sh

# run solver
sh run_solver.sh