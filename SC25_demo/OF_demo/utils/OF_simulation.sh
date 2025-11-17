#!/bin/bash

################################################################################
# OpenFOAM Simulation Script - Runs the actual simulation
# This script is submitted to the queue via qsub
# 
# Called by: runme.sh
# Environment: Set by qsub (NSLOTS for thread count)
################################################################################

set -e

# Setup environment
source ~/.bashrc 2>/dev/null || true
module purge 2>/dev/null || true
module add paraview/5.11.2 2>/dev/null || true
module add openfoam/10.0/gcc/8.5.0 2>/dev/null || true
conda activate xgfabric 2>/dev/null || true

CASE_DIR="$1"

echo "========================================"
echo "OpenFOAM Simulation Started"
echo "========================================"
echo "Case: $CASE_DIR"
echo "Threads: $NSLOTS"
echo "Started: $(date)"

cd "$CASE_DIR" || exit 1
START=$(date '+%s.%N')

# Run simulation
if [ "$NSLOTS" = "1" ]; then
    echo "Running serial simulation..."
    porousSimpleFoam | tee log
else
    echo "Running parallel with $NSLOTS cores..."
    decomposePar -fileHandler uncollated -force > /dev/null 2>&1
    mpirun -np $NSLOTS porousSimpleFoam -parallel | tee log
    reconstructPar > /dev/null 2>&1
fi

END=$(date '+%s.%N')
ELAPSED=$(bc -l <<< "$END - $START")

echo "========================================"
echo "Simulation Completed in $ELAPSED seconds"
echo "Finished: $(date)"
echo "========================================"

echo "========================================"
echo "Creating VTK outputs"
echo "========================================"

foamToVTK -allPatches

echo "========================================"
echo "Rendering Images"
echo "========================================"

cd ..
xvfb-run -a -s "-screen 0 1920x1080x24" pvpython --force-offscreen-rendering "utils/render_foam.py" "$CASE_DIR" 2>/dev/null