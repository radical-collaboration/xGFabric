#!/bin/bash
WORK_DIR=`pwd`
UTILS_DIR="${WORK_DIR}/utils"
for i in "$@"; do
    case $i in
        -j=*|--job_number=*)
            job_number="${i#*=}"
            shift
            ;;
        -l=*|--log_file=*)
            log_file_path="${i#*=}"
            shift
            ;;
        
        -t=*|--threads=*)
            n_threads="${i#*=}"
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        -*|--*)
            echo "Unknown option: $i"
            print_usage
            exit 1
            ;;
        *)
            echo "Unknown option: $i"
            print_usage
            exit 1
            ;;
    esac
done

# copy the template file and fill in the data
curr_time=$(date '+%y-%m-%d_%H_%M_%S')
file="submit_$curr_time.sh"
cp "$UTILS_DIR/template.sh" "scripts/$file"

# add UGE header
new_line="#!/bin/bash\n#$ -pe smp $n_threads\n#$ -q long\njob_number=$job_number \nlog_file_path=$log_file_path\n"
sed -i "1i $new_line" "scripts/$file"

# Submit job and capture job ID
qsub_output=$(qsub -o "logs/job_output_\$JOB_ID.out" "scripts/$file")

if [[ $? -ne 0 ]]; then
    echo "ERROR: Failed to submit job"
    exit 1
fi

echo "Job $job_number: submitted" >> $log_file_path