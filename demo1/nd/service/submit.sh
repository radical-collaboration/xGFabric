#!/bin/bash

# Check for the DISPLAY environment variable
if [ -z "$DISPLAY" ]; then # there is no DISPLAY env
    echo "launching with no display env"
    qsub launch.sh
    cd ../OpenFOAM
    sh generate_plots.sh
else # there is a DISPLAY env
    echo "launching with a display env"
    sh launch.sh
fi