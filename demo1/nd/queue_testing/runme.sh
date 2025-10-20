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
while [ true ]; do

# -------------------------------------------------
#                 4 core jobs
# -------------------------------------------------
    cp template.sh "scripts/submit_4_$idx.sh"

    line_to_prepend="#!/bin/bash\n#$ -q long\n#$ -pe smp 4\nsubmitted_at=$(date '+%s.%N')\nfile=submit_4_$idx.sh\nnum_cores=4\n"
    file="scripts/submit_4_$idx.sh"
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
    echo "submit_4_$idx.sh,$jobs_ahead,$jobs_in_my_queue,$jobs_running,4" >> data/ahead.csv



# -------------------------------------------------
#                16 core jobs
# -------------------------------------------------

    cp template.sh "scripts/submit_16_$idx.sh"

    line_to_prepend="#!/bin/bash\n#$ -q long\n#$ -pe smp 16\nsubmitted_at=$(date '+%s.%N')\nfile=submit_16_$idx.sh\nnum_cores=16\n"
    file="scripts/submit_16_$idx.sh"
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
    echo "submit_16_$idx.sh,$jobs_ahead,$jobs_in_my_queue,$jobs_running,16" >> data/ahead.csv


# -------------------------------------------------
#                64 core jobs
# -------------------------------------------------

    cp template.sh "scripts/submit_64_$idx.sh"

    line_to_prepend="#!/bin/bash\n#$ -q long\n#$ -pe smp 64\nsubmitted_at=$(date '+%s.%N')\nfile=submit_64_$idx.sh\nnum_cores=64\n"
    file="scripts/submit_64_$idx.sh"
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
    echo "submit_64_$idx.sh,$jobs_ahead,$jobs_in_my_queue,$jobs_running,64" >> data/ahead.csv


    idx=$((idx + 1))
    echo "$idx" >> index.log
    sleep 5m
done
