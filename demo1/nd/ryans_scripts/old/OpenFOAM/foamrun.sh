#!/bin/bash

touch out.uge.log

echo "Task started at [$(date '+%Y-%m-%d %H:%M:%S')]" >> out.uge.log

source ./install.sh

# start the script
cd openfoam-partial/combustion/reactingFoam/LES/DLRCJH/piloted/

sh ./Allrun

echo "Task finished at [$(date '+%Y-%m-%d %H:%M:%S')]" >> out.uge.log