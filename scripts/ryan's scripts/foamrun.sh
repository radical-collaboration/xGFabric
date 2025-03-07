#!/bin/bash

# . $WM_PROJECT_DIR/bin/tools/RunFunctions
# Liu adds: It is actually "module load openfoam/10.0"
. /afs/crc.nd.edu/x86_64_linux/o/openfoam/7.0/OpenFOAM-7/bin/tools/RunFunctions
. /afs/crc.nd.edu/x86_64_linux/o/openfoam/7.0/OpenFOAM-7/etc/bashrc

# Run the meshing and preparations
# Liu adds: We do not run this anymore since for current solution no need to update the meshing.
runApplication surfaceFeatures -dict ./system/surfaceFeatureExtractDict
runApplication blockMesh
runApplication snappyHexMesh -overwrite
runApplication topoSet

# Run the solver
# Liu adds: It is just this command to run, 
# but before this, it has to be unpacked from default configuration zip 
# (And if possible, update from CSPOT - that is not possible on ND at the time of the meeting)
runApplication porousSimpleFoam | tee log logs/log_$(date '+%y-%m-%d_%X')
