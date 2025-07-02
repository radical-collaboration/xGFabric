#!/bin/bash
# activate the environment
source ~/.bashrc
conda activate xgfabric

if [ ! -f "$HOME/.cspot/capabilities.yaml" ] ||  [ ! -d "$HOME/.cspot" ]; then
    printf "Could not find the capabilities.yaml file in $HOME/.cspot.\n\nPlease do the following:\n    1. Create or copy over the capabilities.yaml file.\n    2. Run chmod 700 on the $HOME/.cspot folder.\n    3. Run chmod 600 on the capabilities.yaml file.\n"
    exit 1
fi

# check for which machine the user is running
option="-1"
if [ "$1" ]; then
    option="$1"
else
    printf "This script has been tested on the following clusters:\n1. Purdue ANVIL\n2. Notre Dame\n3. Texas Stampede3\n\n==> Which cluster are you running on? (1-3)\n==> "

    read option

    if [ "$option" -eq 1 ]; then
        echo "==> You selected: Purdue ANVIL"
    elif [ "$option" -eq 2 ]; then
        echo "==> You selected: Notre Dame"
    elif [ "$option" -eq 3 ]; then
        echo "==> You selected: Texas Stampede3"
    else
        echo "Invalid selection. Please choose 1, 2, or 3."
        exit 1
    fi
fi

if [ "$option" -eq 1 ] || [ "$option" -eq 2 ]; then
    if [ -z "$DISPLAY" ]; then
        printf "No X11 environment detected (DISPLAY is not set). If you are accessing the machine via SSH, then please reconnect with the -Y flag to pass your display variables.\n\nEX: ssh -Y user@machine.edu\n"
        exit 1
    fi
fi
# check for number of threads to run the program on
n_threads=-1
if [ "$2" ]; then
    n_threads="$2"
else
    printf "How many threads do you want to run this on? (default is 5)\n==> "

    read n_threads

    if [ -z "$n_threads" ]; then
        n_threads=5
    fi

    echo "==> You selected: $n_threads threads"
fi

# check for number of iterations the user wants to perform
seciteration=-1
if [ "$3" ]; then
    seciteration="$3"
else
    printf "How many iterations do you want to compute? (default is 3)\n==> "

    read seciteration

    if [ -z "$seciteration" ]; then
        seciteration=3
    fi

    echo "==> You selected: $seciteration iterations"
fi

folder_name="cups_structure"
destination="${folder_name}_$(date '+%y-%m-%d_%H_%M_%S')"

touch config.ini
echo $n_threads >> config.ini
echo $seciteration >> config.ini
echo $folder_name >> config.ini
echo $destination >> config.ini
echo $option >> config.ini

if [ "$option" -eq 1 ] || [ "$option" -eq 3 ]; then
    if [ "$option" -eq 1 ]; then
        job_id=$(sbatch --ntasks="$n_threads" --mem="16GB" --parsable --output="job_output_%j.out" cups.sh)
    elif [ "$option" -eq 3 ]; then
        job_id=$(sbatch --time="24:0:0" --nodes="1" --partition="skx" --ntasks="$n_threads" --mem="16GB" --parsable --output="job_output_%j.out" cups.sh | tail -n 1)
    fi
    echo "Submitted job: $job_id"

    output_file="job_output_${job_id}.out"

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
    sh render.sh $destination $option

elif [ "$option" -eq 2 ]; then

    # Submit job and capture job ID
    qsub_output=$(qsub -o "job_output_\$JOB_ID.out" "cups.sh")
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

    output_file="job_output_${job_id}.out"

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
    
    sh render.sh $destination $option
else
    echo "An error occured"
fi