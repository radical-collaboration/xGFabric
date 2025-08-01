#!/bin/bash
threads=1
while true; do
    if [ "$threads" -gt 64 ]; then
        break
    fi

    sh runme.sh -t="$threads"
    echo "Submitted a simulation with $threads threads."
    sleep 2

    threads=$((threads * 2))
done

sh runme.sh -t=24
