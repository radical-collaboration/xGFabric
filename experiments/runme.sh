#!/bin/bash
for i in "$@"; do
    case $i in
        -t=*|--threads=*)
            n_threads="${i#*=}"
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

cp cups.sh "submit_$curr_time.sh"
line_to_prepend="threads=$n_threads\nseciteration=2\nfolder_name=$folder_name\ndestination=$destination\n"
file="submit_$curr_time.sh"
sed -i "1i $line_to_prepend" "$file"

new_line="#!/bin/bash\n#$ -q long\n#$ -pe smp $n_threads"

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
