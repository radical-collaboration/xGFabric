#!/bin/bash
WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_DIR="${WORK_DIR}/utils"

print_usage () {
    echo "Usage: ./runme.sh [OPTIONS]"
    echo
    echo "Options:"
    echo "  -c=NUM,  --cluster=1|2|3|4          Set the cluster"
    echo "  -t=NUM,  --threads=NUM              Set the number of threads"
    echo "  -s=NUM,  --seciter=NUM              Set the number of iterations"
    echo "  -r=BOOL, --render=TRUE|false        Set render mode"
    echo "  -b=BOOL, --background=true|FALSE    Submit job in the background"
    echo "  -h,      --help                     Show this help message and exit"
    echo
    echo "Example:"
    echo "    ./runme.sh --cluster=1 --threads=8 --seciter=5 --render=True --background=False"
    echo
    echo "Note:"
    echo "    If you run ths shell script with no arguments, then it will run in an interactive mode."
}

if [[ "$@" == "" ]]; then
    # check for which machine the user is running
    printf "This script has been tested on the following clusters:\n1. Purdue ANVIL\n2. Notre Dame\n3. Texas Stampede3\n4. NERSC\n\n==> Which cluster are you running on? (1-4)\n==> "
    read cluster

    # cluster options
    if [ "$cluster" -eq 1 ]; then
        echo "==> You selected: Purdue ANVIL"
    elif [ "$cluster" -eq 2 ]; then
        echo "==> You selected: Notre Dame"
    elif [ "$cluster" -eq 3 ]; then
        echo "==> You selected: Texas Stampede3"
    elif [ "$cluster" -eq 4 ]; then
        echo "==> You selected: NERSC"
    else
        echo "Invalid selection. Please choose 1, 2, 3, or 4."
        exit 1
    fi

    # check for number of threads to run the program on
    printf "How many threads do you want to run this on? (default is 5)\n==> "
    read n_threads
    if [ -z "$n_threads" ]; then
        n_threads=5
    fi

    echo "==> You selected: $n_threads threads"

    # check for number of iterations the user wants to perform
    printf "How many iterations do you want to compute? (default is 3)\n==> "
    read seciteration

    if [ -z "$seciteration" ]; then
        seciteration=3
    fi

    echo "==> You selected: $seciteration iterations"

    # check is user wants to render the output
    printf "Would you like to render the output of OpenFOAM? [y]/n\n==> "
    read render

    if [[ "$render" == "" ]]; then
        render="yes"
    fi

    echo "==> You selected: $render"

else
    for i in "$@"; do
        case $i in
            -c=*|--cluster=*)
                cluster="${i#*=}"
                shift
                ;;
            -t=*|--threads=*)
                n_threads="${i#*=}"
                shift
                ;;
            -s=*|--seciter=*)
                seciteration="${i#*=}"
                shift
                ;;
            -r=*|--render=*)
                lower="${i#*=}"
                render="${lower,,}"
                shift
                ;;
            -b=*|--background=*)
                lower="${i#*=}"
                background="${lower,,}"
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
fi

# activate the environment
sh $UTILS_DIR/env_setup.sh

# check if user wants to render the output
case "$render" in
    yes|y|true|t|"")
        render=true
        ;;
    no|n|false|f)
        render=false
        ;;
    *)
        echo "Unknown option $render"
        exit 1
        ;;
esac

# check if user wants to run the task in the background
case "$background" in
    yes|y|true|t)
        background=true
        ;;
    no|n|false|f|"")
        background=false
        ;;
    *)
        echo "Unknown option $background"
        exit 1
        ;;
esac


folder_name="cups_structure"
curr_time=$(date '+%y-%m-%d_%H_%M_%S')
output_folder="output/${curr_time}"
mkdir -p "$output_folder"
destination="$output_folder/${folder_name}_$curr_time"
file="$output_folder/submit_$curr_time.sh"

cp "$UTILS_DIR/cups.sh" "$file"
line_to_prepend="threads=$n_threads\nseciteration=$seciteration\nfolder_name=$folder_name\ndestination=$destination\ncluster=$cluster\nrender=$render\nWORK_DIR=$WORK_DIR\nUTILS_DIR=$UTILS_DIR\n"
sed -i "1i $line_to_prepend" "$file"

if [ "$cluster" -eq 1 ] || [ "$cluster" -eq 3 ]; then
    new_line="#!/bin/bash"
    sed -i "1i $new_line" "$file"

    if [ "$cluster" -eq 1 ]; then
        job_id=$(sbatch --ntasks="$n_threads" --mem="16GB" --time="24:0:0" --parsable --output="$output_folder/job_output_%j.out" "$file")
    elif [ "$cluster" -eq 3 ]; then
        job_id=$(sbatch --time="24:0:0" --nodes="1" --partition="skx" --ntasks="$n_threads" --mem="16GB" --parsable --output="$output_folder/job_output_%j.out" "$file" | tail -n 1)
    fi

    if [[ "$background" == "false" ]]; then
        echo "Submitted job: $job_id"

        output_file="$output_folder/job_output_${job_id}.out"

        # Wait for output file to be created
        while [[ ! -f "$output_file" ]]; do
            sleep 5
        done

        # Monitor output in real-time
        echo "=== Real-time Job Output ==="
        tail -f "$output_file" &
        tail_pid=$!

        # Wait for job completion
        while squeue -j $job_id 2>/dev/null | grep -q $job_id; do
            sleep 10
        done

        # Stop tailing and show final status
        kill $tail_pid 2>/dev/null
        echo "Job $job_id completed"

        # generate images
        if [[ "$render" == "true" ]]; then
            sh $UTILS_DIR/render.sh $destination $cluster
        fi
    fi

elif [ "$cluster" -eq 2 ]; then
    new_line="#!/bin/bash\n#$ -pe smp $n_threads\n#$ -q long"
    sed -i "1i $new_line" "$file"

    # Submit job and capture job ID
    qsub_output=$(qsub -o "$output_folder/job_output_\$JOB_ID.out" "$file")

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

    if [[ "$background" == "false" ]]; then
        output_file="$output_folder/job_output_${job_id}.out"

        # Wait for output file to be created
        echo "Waiting for output file to be created..."
        while [[ ! -f "$output_file" ]]; do
            sleep 5
        done

        echo "Output file created: $output_file"

        # Monitor output in real-time
        echo "=== Real-time Job Output ==="
        tail -f "$output_file" &
        tail_pid=$!

        # Wait for job completion
        while qstat -j $job_id >/dev/null 2>&1; do
            sleep 10
        done

        # Stop tailing and show final status
        kill $tail_pid 2>/dev/null
        echo ""
        echo "==================="
        echo "Job $job_id completed"
        
        if [[ "$render" == "true" ]]; then
            sh $UTILS_DIR/render.sh $destination $cluster
        fi
    fi
elif [ "$cluster" -eq 4 ]; then
    new_line="#!/bin/bash"
    sed -i "1i $new_line" "$file"

    acc=$(sacctmgr show user "$USER" | awk 'NR==3 {print $2}')

    job_id=$(sbatch --time="2:0:0" --ntasks-per-node=$n_threads --nodes=1 --ntasks=$n_threads --constraint=cpu --qos=regular --account="$acc" --mem=16GB --parsable --output="$output_folder/job_output_%j.out" "$file" | tail -n 1)

    if [[ "$background" == "false" ]]; then
        echo "Submitted job: $job_id"

        output_file="$output_folder/job_output_${job_id}.out"

        # Wait for output file to be created
        while [[ ! -f "$output_file" ]]; do
            sleep 5
        done

        # Monitor output in real-time
        echo "=== Real-time Job Output ==="
        tail -f "$output_file" &
        tail_pid=$!

        # Wait for job completion
        while squeue -j $job_id 2>/dev/null | grep -q $job_id; do
            sleep 10
        done

        # Stop tailing and show final status
        kill $tail_pid 2>/dev/null
        echo "Job $job_id completed"

        # generate images
        if [[ "$render" == "true" ]]; then
            sh $UTILS_DIR/render.sh $destination $cluster
        fi
    fi
else
    echo "An error occured"
fi