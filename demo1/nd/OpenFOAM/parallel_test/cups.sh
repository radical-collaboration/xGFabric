#!/bin/bash
threads=$(sed -n '1p' config.ini)
seciteration=$(sed -n '2p' config.ini)
folder_name=$(sed -n '3p' config.ini)
destination=$(sed -n '4p' config.ini)
cluster=$(sed -n '5p' config.ini)
render=$(sed -n '6p' config.ini)

rm config.ini

source ~/.bashrc
conda activate xgfabric

if [ "$cluster" -eq 1 ]; then
    module load gcc/11.2.0
    module load openmpi/4.0.6
    module load openfoam/8-20210316
    source $FOAM_ETC/bashrc
    module load paraview/5.10.1
elif [ "$cluster" -eq 2 ]; then
    module add openfoam/10.0/gcc/8.5.0 > /dev/null 2>&1
    module add paraview/5.11.2
elif [ "$cluster" -eq 3 ]; then
    module purge
    module load intel/23.1 impi/21.9 openfoam/8 paraview/5.12.0
    export LD_LIBRARY_PATH=/opt/intel/oneapi/mpi/2021.11/lib:$LD_LIBRARY_PATH
fi


if ! [ -f cups_structure.zip ]; then
    wget https://notredame.box.com/shared/static/j1nv30fb4vjerbwcc4nqogqi34rdnjj6.zip -O cups_structure.zip
fi

start=$(date '+%s.%N')

if ! [ -d "logs" ]; then
    mkdir "logs"
fi

# 3. Load most recent online data
b=$(senspot-get -W woof://169.231.230.76/sharedfs/unl-data/daviscupsout)
vals=$(awk -F" " '{print $1}' <<< "$b")
windspeed=$(awk -F":" '{print $4}' <<< "$vals")
winddir=$(awk -F":" '{print $7}' <<< "$vals")

if [ -z "$windspeed" ]; then
    windspeed="2"
fi

if [ -z "$winddir" ]; then
    windspeed="NW"
fi

echo $destination

unzip -q $folder_name
mv $folder_name $destination


python3 replace.py spare_details/system/decomposeParDict "$destination/system/decomposeParDict" @ $threads
python3 replace.py spare_details/system/controlDict "$destination/system/controlDict" @ $seciteration

# Ensure the folder exists
if [ ! -d "$destination" ]; then
    echo "Directory '$destination' does not exist."
    exit 1
fi

# Find all regular files recursively in the folder
find "$destination" -type f | while read -r file; do
    # Check if the file contains 'FoamFile' followed by '{'
    if grep -q 'FoamFile' "$file" && grep -q '{' "$file"; then
        # Check if 'version     8.0;' already exists
        if ! grep -q 'version     8.0;' "$file"; then
            # Use awk to insert the version line after the first '{' following 'FoamFile'
            awk '
            BEGIN {inFoamBlock=0}
            /FoamFile/ {inFoamBlock=1; print; next}
            inFoamBlock && /^\s*{/ {
                print;
                print "    version     8.0;";
                inFoamBlock=0;
                next
            }
            {print}
            ' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
            # echo "Updated: $file"
        # else
        #     echo "Already has version line: $file"
        fi
    # else
    #     echo "No FoamFile block found: $file"
    fi
done

echo "windspeed winddir $windspeed $winddir"
python3 update.py $windspeed $winddir -f $destination

# 5. Run solver to perform the calculation
cd $destination
# For parallel version (scripted for now)
touch "../logs/$threads-$destination"

exit 0
if [ "$threads" -eq 1 ]; then
    porousSimpleFoam | tee "../logs/$threads-$destination"
else
    decomposePar -fileHandler uncollated -force
    p_start=$(date '+%s.%N')
    mpirun -n $threads porousSimpleFoam -parallel | tee "../logs/$threads-$destination"
    p_stop=$(date '+%s.%N')
    p_elapsed=$(bc -l <<< "$p_stop - $p_start")
    echo "Reconstruction started"
    reconstructPar
fi

stop=$(date '+%s.%N')
elapsed=$(bc -l <<< "$stop - $start")
echo "Run of $destination on $(date '+%y-%m-%d_%H_%M_%S') and $threads threads till $seciteration sec/iteration took $elapsed sec ($p_elapsed); $4" >> ../result_time

if [[ "$render" == "true" ]]; then
    foamToVTK -allPatches
fi

cd ..
