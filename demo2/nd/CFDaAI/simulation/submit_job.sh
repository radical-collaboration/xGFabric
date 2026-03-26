#!/bin/bash

# Submit OpenFOAM simulation as a cluster job using qsub
# Usage: ./submit_job.sh <x_wind> <y_wind> <z_wind> [--threads=N] [--nodes=N]
# Example: ./submit_job.sh 2.5 0.0 0.0 --threads=32

# Parse arguments
X_WIND=""
Y_WIND=""
Z_WIND=""
THREADS=32
NODES=1

for arg in "$@"; do
    case $arg in
        -t=*|--threads=*)
            THREADS="${arg#*=}"
            shift
            ;;
        -n=*|--nodes=*)
            NODES="${arg#*=}"
            shift
            ;;
        *)
            if [ -z "$X_WIND" ]; then
                X_WIND=$arg
            elif [ -z "$Y_WIND" ]; then
                Y_WIND=$arg
            elif [ -z "$Z_WIND" ]; then
                Z_WIND=$arg
            fi
            shift
            ;;
    esac
done

# Check arguments
if [ -z "$X_WIND" ] || [ -z "$Y_WIND" ] || [ -z "$Z_WIND" ]; then
    echo "Usage: $0 <x_windspeed> <y_windspeed> <z_windspeed> [--threads=N] [--nodes=N]"
    echo "Example: $0 2.5 0.0 0.0 --threads=32 --nodes=1"
    exit 1
fi

# Activate environment
source ~/.bashrc
conda activate xgfabric 2>/dev/null || true

# Calculate total cores
TOTAL_CORES=$((THREADS * NODES))

# Create timestamp
TIMESTAMP=$(date '+%y-%m-%d_%H_%M_%S')
JOB_SCRIPT="submit_${TIMESTAMP}.sh"

# Create job submission script
cat > "$JOB_SCRIPT" <<EOF
#!/bin/bash
#$ -q long
#$ -pe mpi-${THREADS} ${TOTAL_CORES}
#$ -o job_output_\$JOB_ID.out
#$ -j y
set -e

# Job parameters
NODES=${NODES}
TOTAL_CORES=${TOTAL_CORES}
THREADS=${THREADS}
X_WIND=${X_WIND}
Y_WIND=${Y_WIND}
Z_WIND=${Z_WIND}

# Activate environment
source ~/.bashrc
conda activate xgfabric 2>/dev/null || true

# Run the simulation
bash runme.sh cups_structure.zip \${THREADS} \${X_WIND} \${Y_WIND} \${Z_WIND}

echo "Job completed successfully"
EOF

# Submit the job
echo "Submitting job with:"
echo "  Wind speed: ($X_WIND, $Y_WIND, $Z_WIND) m/s"
echo "  Threads: $THREADS"
echo "  Nodes: $NODES"
echo "  Total cores: $TOTAL_CORES"

qsub_output=$(qsub "$JOB_SCRIPT")

if [[ $? -ne 0 ]]; then
    echo "ERROR: Failed to submit job"
    exit 1
fi

# Extract job ID
job_id=$(echo "$qsub_output" | grep -oE '[0-9]+' | head -1)

if [[ -z "$job_id" ]]; then
    echo "ERROR: Could not extract job ID from: $qsub_output"
    exit 1
fi

echo "Job submitted successfully!"
echo "Job ID: $job_id"
echo "Job script: $JOB_SCRIPT"
echo ""
echo "Monitor job with: qstat"
echo "View output with: tail -f job_output_${job_id}.out"
