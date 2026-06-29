#!/bin/bash
# activate environment
conda activate cfdaai

source "env/system_config.sh"
source "lib/common.sh"
source "lib/simulations.sh"
source "data/data_source.sh"
source "env/system_config.sh"
# source "env/env_nersc.sh"


module --force purge
module load spack
. /global/common/software/nersc9/spack/1.1.0/share/spack/setup-env.sh
module load conda
module load paraview || true  # paraview may not be needed at runtime
spack load openmpi@4.1.5
group_num=$NERSC_PROJECT_ID
export OPENFOAM_ROOT="/global/common/software/$group_num/openfoam"
source "$OPENFOAM_ROOT/OpenFOAM-dev/etc/bashrc" || true  # non-fatal: OF env may already be set
export LD_LIBRARY_PATH=$(spack location -i openmpi@4.1.5)/lib:$LD_LIBRARY_PATH

# Check OpenFOAM (optional for some tasks)
if command -v foamToVTK &>/dev/null; then
    log_info "OpenFOAM tools verified"
else
    log_warn "OpenFOAM foamToVTK not found"
fi

log_info "System initialization complete"
