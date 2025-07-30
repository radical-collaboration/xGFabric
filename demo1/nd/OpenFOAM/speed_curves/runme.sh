#!/bin/bash
for i in "$@"; do
    case $i in
        -t=*|--threads=*)
            n_threads="${i#*=}"
            shift
            ;;
        -n=*|--nodes=*)
            n_nodes="${i#*=}"
            shift
            ;;
    esac
done

# activate the environment
source ~/.bashrc
conda activate xgfabric

folder_name="cups_structure"
curr_time=$(date '+%y-%m-%d_%H_%M_%S')
destination="${folder_name}_$curr_time"

if ! [ -f cups_structure.zip ]; then
    wget https://notredame.box.com/shared/static/j1nv30fb4vjerbwcc4nqogqi34rdnjj6.zip -O cups_structure.zip
fi

cp cups.sh "submit_$curr_time.sh"
line_to_prepend="threads=$n_threads\nseciteration=2\nfolder_name=$folder_name\ndestination=$destination\n"
file="submit_$curr_time.sh"
sed -i "1i $line_to_prepend" "$file"


total_cores=$(("$n_threads" * "$n_nodes"))

# The smp environment is for multi-threaded single node runs (single-node experiments)
# new_line="#!/bin/bash\n#$ -q long\n#$ -pe smp $n_threads\nnodes=$n_nodes\ntotal_cores=$total_cores"

# The long queue is for 64 core machines (multi-node experiments)
# new_line="#!/bin/bash\n#$ -q long\n#$ -pe mpi-$n_threads $total_cores\nnodes=$n_nodes\ntotal_cores=$total_cores"

# The hpc queue is for 48 core machines (multi-node experiments)
# new_line="#!/bin/bash\n#$ -q hpc\n#$ -pe mpi-$n_threads $total_cores\nnodes=$n_nodes\ntotal_cores=$total_cores"

sed -i "1i $new_line" "$file"

# Submit job and capture job ID
qsub_output=$(qsub -o "job_output_\$JOB_ID.out" "$file")

if [[ $? -ne 0 ]]; then
    echo "ERROR: Failed to submit job"
    exit 1
fi

# Extract job ID from qsub output
job_id=$(echo "$qsub_output" | grep -oE '[0-9]+' | head -1)

if [[ -z "$job_id" ]]; then
    echo "ERROR: Could not extract job ID from: $qsub_output"
    exit 1
fi

echo "Submitted job: $job_id"
