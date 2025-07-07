#!/bin/bash
threads=1
while true; do
    if [ "$threads" -gt 4 ]; then
        break
    fi

    sh runme.sh -c=2 -t="$threads" -s=3 -r=false -b=true
    echo "Submitted a simulation with $threads threads."
    sleep 2

    threads=$((threads * 2))
done
