#!/bin/bash
if ! [ -d "scripts" ]; then
    mkdir "scripts"
fi

if ! [ -d "logs" ]; then
    mkdir "logs"
fi

if ! [ -f "data/index.log" ]; then
    touch data/index.log
    echo "1" >> data/index.log
fi

idx="$(tail -n 1 data/index.log)"
p_start=$(date '+%s')
machine=1 # ANVIL
# machine=2 # Notre Dame
# machine=3 # TACC Stampede3

declare -a cores=("4" "16" "64")

while [ true ]; do
    for num_cores in "${cores[@]}"; do
        cp template.sh "scripts/submit_${num_cores}_${idx}.sh"

        if [ $machine -eq 1 ]; then # ANVIL
            line_to_prepend="#!/bin/bash\nsubmitted_at=$(date '+%s.%N')\nfile=submit_${num_cores}_${idx}.sh\nnum_cores=${num_cores}\n"
            file="scripts/submit_${num_cores}_${idx}.sh"
            sed -i "1i $line_to_prepend" "$file"

            job_id=$(sbatch --ntasks="$num_cores" --mem="16GB" --time="1:0:0" --parsable --output="logs/job_output_%j.out" "$file")

            jobs_ahead=$(squeue -p long -t PD -o "%.18i" | tail -n +2 | grep -n "^$job_id$" | cut -d: -f1 | awk '{print $1-1}')
            jobs_ahead=${jobs_ahead:-0}
            jobs_in_my_queue=$(squeue -u $USER | tail -n +2 | wc -l)
            jobs_running=$(squeue -u $USER -t R | tail -n +2 | wc -l)

            echo "Submitted job ==> $job_id"
            echo "ID =============> $idx"
            echo "Jobs ahead =====> $jobs_ahead"
            echo "Running for ====> $(bc -l <<< "$(date '+%s') - $p_start") seconds"
            echo "------------------------------------"
            echo "submit_${num_cores}_${idx}.sh,$jobs_ahead,$jobs_in_my_queue,$jobs_running,${num_cores}" >> data/ahead.csv

        elif [ $machine -eq 2 ]; then # Notre Dame
            line_to_prepend="#!/bin/bash\n#$ -q long\n#$ -pe smp $num_cores\nsubmitted_at=$(date '+%s.%N')\nfile=submit_${num_cores}_${idx}.sh\nnum_cores=${num_cores}\n"
            file="scripts/submit_${num_cores}_${idx}.sh"
            sed -i "1i $line_to_prepend" "$file"

            qsub_output=$(qsub -o "logs/job_output_\$JOB_ID.out" "$file")
            job_id=$(echo "$qsub_output" | grep -oE '[0-9]+' | head -1)

            jobs_ahead=$(qstat -q long -s p | awk -v job_id="$job_id" 'NR>1 {if($1==job_id) exit; count++} END {print count}')
            jobs_in_my_queue=$(qstat -u $USER | tail -n +3 | wc -l)
            jobs_running=$(qstat -u $USER -s r | tail -n +3 | wc -l)

            echo "Submitted job ==> $job_id"
            echo "ID =============> $idx"
            echo "Jobs ahead =====> $jobs_ahead"
            echo "Running for ====> $(bc -l <<< "$(date '+%s') - $p_start") seconds"
            echo "------------------------------------"
            echo "submit_${num_cores}_${idx}.sh,$jobs_ahead,$jobs_in_my_queue,$jobs_running,${num_cores}" >> data/ahead.csv

        elif [ $machine -eq 3 ]; then # TACC Stampede3

            line_to_prepend="#!/bin/bash\nsubmitted_at=$(date '+%s.%N')\nfile=submit_${num_cores}_${idx}.sh\nnum_cores=${num_cores}\n"
            file="scripts/submit_${num_cores}_${idx}.sh"
            sed -i "1i $line_to_prepend" "$file"

            job_id=$(sbatch --time="1:0:0" --nodes="1" --partition="icx" --ntasks="$num_cores" --mem="16GB" --parsable --output="logs/job_output_%j.out" "$file" | tail -n 1)

            jobs_ahead=$(squeue -p long -t PD -o "%.18i" | tail -n +2 | grep -n "^$job_id$" | cut -d: -f1 | awk '{print $1-1}')
            jobs_ahead=${jobs_ahead:-0}
            jobs_in_my_queue=$(squeue -u $USER | tail -n +2 | wc -l)
            jobs_running=$(squeue -u $USER -t R | tail -n +2 | wc -l)

            echo "Submitted job ==> $job_id"
            echo "ID =============> $idx"
            echo "Jobs ahead =====> $jobs_ahead"
            echo "Running for ====> $(bc -l <<< "$(date '+%s') - $p_start") seconds"
            echo "------------------------------------"
            echo "submit_${num_cores}_${idx}.sh,$jobs_ahead,$jobs_in_my_queue,$jobs_running,${num_cores}" >> data/ahead.csv
        fi
    done

    idx=$((idx + 1))
    echo "$idx" >> data/index.log
    sleep 5m
done
