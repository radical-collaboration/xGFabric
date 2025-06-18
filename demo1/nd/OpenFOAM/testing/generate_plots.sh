#!/bin/bash
source ~/.bashrc
conda activate xgfabric

# add OpenFOAM module to computer
module add openfoam/10.0/gcc/8.5.0
module add paraview/5.11.2

cd damBreak

foamToVTK -allPatches

cd ..

pvpython --force-offscreen-rendering render_foam.py

python create_gif.py