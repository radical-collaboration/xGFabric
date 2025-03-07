#!/bin/bash

# . $WM_PROJECT_DIR/bin/tools/RunFunctions
. /afs/crc.nd.edu/x86_64_linux/o/openfoam/7.0/OpenFOAM-7/bin/tools/RunFunctions
. /afs/crc.nd.edu/x86_64_linux/o/openfoam/7.0/OpenFOAM-7/etc/bashrc

# Run the meshing and preparations
runApplication surfaceFeatures -dict ./system/surfaceFeatureExtractDict
runApplication blockMesh
runApplication snappyHexMesh -overwrite
runApplication topoSet

# Run the solver
runApplication porousSimpleFoam | tee log logs/log_$(date '+%y-%m-%d_%X')
