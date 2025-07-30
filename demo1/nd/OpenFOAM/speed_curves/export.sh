#!/bin/bash
# Usage: ./export.sh /path/to/openfoam/case [N]
# N is the number of latest time directories to process (default: 1)

set -e

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: $0 <OpenFOAM case directory> [N]"
    echo "  N: number of latest time directories to process (default: 1)"
    exit 1
fi

CASE_DIR="$1"
N="${2:-1}"  # Default to 1 if N is not provided
cd "$CASE_DIR"

# Load OpenFOAM module (as in runme scripts)
module load openfoam/10.0/gcc/8.5.0

# Setup or activate conda environment with meshio
CONDA_ENV="meshio_env"
source $(conda info --base)/etc/profile.d/conda.sh
if conda info --envs | grep -q "$CONDA_ENV"; then
    echo "Activating existing conda environment: $CONDA_ENV"
    conda activate $CONDA_ENV
else
    echo "Creating conda environment: $CONDA_ENV and installing meshio/pandas"
    conda create -y -n $CONDA_ENV python=3.10
    conda activate $CONDA_ENV
    pip install meshio pandas tqdm
fi

# Find the latest N time directories (iterations)
TIME_DIRS=$(ls -d [0-9]* | sort -n | tail -$N)

echo "Processing the last $N time directories: $TIME_DIRS"

# Process each time directory
for TIME_DIR in $TIME_DIRS; do
    echo "Processing time directory: $TIME_DIR"
    
    # Export results (U and p fields) to CSV
    postProcess -func 'writeCellCentres' -time "$TIME_DIR"
    
    # Convert U and p fields to CSV
    # Convert OpenFOAM results to VTK format with specific name
    foamToVTK -time "$TIME_DIR"
done

cd ..
# Run Python script to convert the specific VTK file to CSV
python vtk_to_csv.py $CASE_DIR $N 
echo "CSV conversion complete for $N files."
python verify.py $CASE_DIR

