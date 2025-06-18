#!/bin/bash

# touch out.log

#echo "Task started at [$(date '+%Y-%m-%d %H:%M:%S')]" >> out.log

source ~/.bashrc
conda activate xgfabric

# add OpenFOAM module to computer
module add openfoam/10.0/gcc/8.5.0
module add paraview/5.11.2

source ./install.sh

# start the script
cd damBreak

sh ./Allrun

interFoam | tee log.interFoam

foamLog log.interFoam

# Directory containing the log files
log_dir="logs"

cd ..

# Check for the DISPLAY environment variable
if [ -z "$DISPLAY" ]; then
    echo "No X11 environment detected (DISPLAY is not set). Exiting..."
else
    echo "X11 environment detected (DISPLAY=$DISPLAY). Generating images..."
    sh generate_plots.sh
fi
#echo "Task finished at [$(date '+%Y-%m-%d %H:%M:%S')]" >> out.log
