#!/bin/bash

# Run OpenFOAM simulation
# Usage: ./run_simulation.sh <case_directory> [threads]

# Timing utility
format_duration() {
    local duration="$1"
    local hours=$((duration / 3600))
    local minutes=$(((duration % 3600) / 60))
    local seconds=$((duration % 60))
    echo "${hours}h ${minutes}m ${seconds}s"
}

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <case_directory> [threads]"
    exit 1
fi

CASE_DIR=$1
THREADS=${2:-1}

if [ ! -d "$CASE_DIR" ]; then
    echo "Error: Case directory $CASE_DIR does not exist"
    exit 1
fi

echo "Running OpenFOAM simulation in $CASE_DIR with $THREADS threads"

# Source OpenFOAM environment with proper error checking
if [ "$SYSTEM_TYPE" == "nd" ]; then
    module --force purge
    module add openfoam/10.0/gcc/11.5.0 > /dev/null 2>&1
    module add paraview/5.11.2
elif [ "$SYSTEM_TYPE" == "nersc" ]; then
    module --force purge
    module load spack
    . /global/common/software/nersc9/spack/1.1.0/share/spack/setup-env.sh
    module load conda
    module load paraview || true  # paraview may not be needed at runtime
    spack load openmpi@4.1.5
    group_num=$(groups | awk -F" " '{print $2}')
    export OPENFOAM_ROOT="/global/common/software/$group_num/openfoam"
    source "$OPENFOAM_ROOT/OpenFOAM-dev/etc/bashrc" || true  # non-fatal: OF env may already be set
    export LD_LIBRARY_PATH=$(spack location -i openmpi@4.1.5)/lib:$LD_LIBRARY_PATH
elif [ -n "$FOAM_BASH" ]; then
    source $FOAM_BASH
elif [ -n "$FOAM_ETC" ]; then
    source $FOAM_ETC/bashrc
else
    echo "Sourcing OpenFOAM from /opt/openfoam11..."
    # Try common installation paths
    if [ -f /opt/openfoam11/etc/bashrc ]; then
        source /opt/openfoam11/etc/bashrc
    elif [ -f /opt/openfoam/etc/bashrc ]; then
        source /opt/openfoam/etc/bashrc
    elif [ -f /usr/lib/openfoam/etc/bashrc ]; then
        source /usr/lib/openfoam/etc/bashrc
    else
        echo "Error: Could not find OpenFOAM installation at /opt/openfoam11"
        exit 1
    fi
fi

cd "$CASE_DIR" || { echo "Error: Failed to change to case directory"; exit 1; }

START_TIME=$(date '+%s.%N')
START_TIME_INT=$(date '+%s')
echo "[TIMER] Simulation started at $(date '+%Y-%m-%d %H:%M:%S')"

# Run the solver
if [ "$THREADS" -eq 1 ]; then
    echo "Running serial simulation..."
    if ! porousSimpleFoam | tee log; then
        echo "Error: Serial simulation failed"
        exit 1
    fi
else
    echo "Running parallel simulation with $THREADS cores..."
    
    # Decompose domain
    DECOMP_START=$(date '+%s')
    echo "[TIMER] Domain decomposition started at $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Decomposing domain..."
    if ! decomposePar -force > decomposePar.log 2>&1; then
        echo "Error: decomposePar failed. Log:"
        cat decomposePar.log
        exit 1
    fi
    DECOMP_END=$(date '+%s')
    DECOMP_ELAPSED=$((DECOMP_END - DECOMP_START))
    echo "[TIMER] Domain decomposition completed - Duration: $(format_duration $DECOMP_ELAPSED) (${DECOMP_ELAPSED}s)"
    
    # Run parallel simulation
    SOLVER_START=$(date '+%s')
    echo "[TIMER] Solver (porousSimpleFoam) started at $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Running solver on $THREADS cores..."
    if ! mpirun -np "$THREADS" porousSimpleFoam -parallel | tee log; then
        echo "Error: Parallel simulation failed"
        exit 1
    fi
    SOLVER_END=$(date '+%s')
    SOLVER_ELAPSED=$((SOLVER_END - SOLVER_START))
    echo "[TIMER] Solver completed - Duration: $(format_duration $SOLVER_ELAPSED) (${SOLVER_ELAPSED}s)"
    
    # Reconstruct results
    RECON_START=$(date '+%s')
    echo "[TIMER] Result reconstruction started at $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Reconstructing parallel results..."
    if ! reconstructPar -latestTime > reconstructPar.log 2>&1; then
        echo "Error: reconstructPar failed. Log:"
        cat reconstructPar.log
        exit 1
    fi
    RECON_END=$(date '+%s')
    RECON_ELAPSED=$((RECON_END - RECON_START))
    echo "[TIMER] Result reconstruction completed - Duration: $(format_duration $RECON_ELAPSED) (${RECON_ELAPSED}s)"
    
    # Clean up processor directories to save disk space
    CLEANUP_START=$(date '+%s')
    echo "Cleaning up processor directories to save disk space..."
    rm -rf processor* 2>/dev/null || true
    echo "Processor directories removed"
    CLEANUP_END=$(date '+%s')
    CLEANUP_ELAPSED=$((CLEANUP_END - CLEANUP_START))
    echo "[TIMER] Processor cleanup completed - Duration: ${CLEANUP_ELAPSED}s"
fi

END_TIME=$(date '+%s.%N')
END_TIME_INT=$(date '+%s')
ELAPSED=$(bc -l <<< "$END_TIME - $START_TIME")
ELAPSED_INT=$((END_TIME_INT - START_TIME_INT))

echo "Simulation completed in $ELAPSED seconds"
echo "[TIMER] Total simulation time: $(format_duration $ELAPSED_INT) (${ELAPSED_INT}s)"
echo "[TIMER] Simulation completed at $(date '+%Y-%m-%d %H:%M:%S')"

cd .. || exit 1
