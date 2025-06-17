#!/bin/bash
if conda env list | grep -q "nd-xgfabric"
then
    echo "already created fabric environment"
else
    echo "creating fabric environment"
    conda env create -f ../../environment.yml
fi

source ~/.bashrc
conda activate nd-xgfabric


echo -n "This script has been tested on the following clusters:
1. Purdue ANVIL
2. Notre Dame
3. Texas Stampede3

==> Which cluster are you running on? (1-3)
==> "

read cluster_choice

option=-1

case $cluster_choice in
    1)
        echo "==> You selected: Purdue ANVIL"
        module load gcc/11.2.0
        module load openmpi/4.0.6
        module load openfoam/8-20210316
        source $FOAM_ETC/bashrc
        module load paraview/5.10.1
        option=1
        ;;
    2)
        echo "==> You selected: Notre Dame"
        module add openfoam/10.0/gcc/8.5.0
        module add paraview/5.11.2
        option=2
        ;;
    3)
        echo "==> You selected: Texas Stampede3"
        ;;
    *)
        echo "Invalid selection. Please choose 1, 2, or 3."
        exit 1
        ;;
esac

n_slots=3 # number of nodes
n_threads=3 # number of cores
seciteration=2
folder_name="cups_structure"
destination="${folder_name}_$(date '+%y-%m-%d_%H_%M_%S')"

touch config.ini
echo $n_slots >> config.ini
echo $n_threads >> config.ini
echo $seciteration >> config.ini
echo $folder_name >> config.ini
echo $destination >> config.ini
echo $option >> config.ini

if [ "$option" -eq 1 ]; then
    job_id=$(sbatch --parsable --output="job_output_%j.out" cups.sh)
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

    # Get final job status using qacct (if available)
    echo "Retrieving final job status..."
    sleep 5  # Wait for accounting data

    job_accounting=$(qacct -j $job_id 2>/dev/null)
    if [[ $? -eq 0 ]]; then
        exit_status=$(echo "$job_accounting" | grep "^exit_status" | awk '{print $2}')
        failed=$(echo "$job_accounting" | grep "^failed" | awk '{print $2}')
        ru_wallclock=$(echo "$job_accounting" | grep "^ru_wallclock" | awk '{print $2}')
        
        echo "Exit Status: $exit_status"
        echo "Failed Code: $failed"
        echo "Wall Clock Time: $ru_wallclock seconds"
        
        if [[ "$exit_status" == "0" && "$failed" == "0" ]]; then
            echo "Final State: COMPLETED"
        else
            echo "Final State: FAILED"
        fi
    else
        echo "Could not retrieve accounting information (job may have just finished)"
    fi

else
    echo "An error occured"
fi

sh render.sh $destination