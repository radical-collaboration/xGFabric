#!/bin/bash
threads=1
while true; do
    if [ "$threads" -gt 1 ]; then
        break
    fi

    sh runme.sh -c=2 -t="$threads" -s=50 -r=false -b=true
    echo "Submitted a simulation with $threads threads."
    sleep 2

    threads=$((threads * 2))
done

./runme.sh --cluster=2 --threads=8 --seciter=5 --render=False --background=False