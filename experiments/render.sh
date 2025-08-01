#!/bin/bash
destination="$1"
source ~/.bashrc
module purge
module add openfoam/10.0/gcc/8.5.0 > /dev/null 2>&1
module add paraview/5.11.2


cd $destination
foamToVTK -latestTime
cd ..

pvpython --force-offscreen-rendering render_foam.py $destination

echo "Script completed successfully!"
echo "Check png_outputs directory for visualization outputs"