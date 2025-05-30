#!/bin/bash
#$ -q long
#$ -pe mpi-64 64
##########$ -pe mpi-48 48
threads=64
seciteration=50
folder_name="cups_structure"
if [ -n "$1" ]; then
  folder_name="$1"
fi

if [ -n "$2" ]; then
  threads="$2"
fi

if [ -n "$3" ]; then
  seciteration="$3"
fi

if ! [ -f cups_structure.zip ]; then
  wget https://notredame.box.com/s/j1nv30fb4vjerbwcc4nqogqi34rdnjj6 -O cups_structure.zip
fi


destination="${folder_name}_$(date '+%y-%m-%d_%H_%M_%S')"

#if pgrep -x "python host_results.py"; then
#  echo "Killing previous flask and running new"
#  kill $process_id
#fi
#rm static/*
#kill $(ps aux | grep '.+python.+host_results.py' | awk '{print $2}')
#nohup python3 host_results.py > flask.logs &

start=$(date '+%s.%N')
# 1. Install openfoam if needed
# https://openfoam.org/download/10-ubuntu/

# 2. Load openfoam
module add openfoam/10.0/gcc/8.5.0
module add paraview/5.11.2

if conda env list | grep -q "nd-xgfabric"
then
   echo "already created fabric environment"
else
   echo "creating fabric environment"
   conda env create -f ../environment.yml
fi
conda activate nd-xgfabric

# 3. Load most recent online data # Not working on ND as of now
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

# 4. Unpack zip and update it with data
#python3 unzip_and_update.py $windspeed $winddir --file cfd_test.zipcups_structure.zip
rm -r $folder_name
#rm png_outputs/*
echo $destination

unzip $folder_name
mv $folder_name $destination


#cp -r spare_details/* $destination
python3 replace.py spare_details/system/decomposeParDict "$destination/system/decomposeParDict" @ $threads
python3 replace.py spare_details/system/controlDict "$destination/system/controlDict" @ $seciteration

echo "windspeed winddir $windspeed $winddir"
python3 update.py $windspeed $winddir -f $destination

# 5. Run solver to perform the calculation
cd $destination
# For parallel version (sciped for now)
if [ "$threads" -eq 1 ]; then
  porousSimpleFoam | tee log logs/log_$(date '+%y-%m-%d_%H_%M_%S')
else
  decomposePar
  #sbatch -n $threads
  p_start=$(date '+%s.%N')
  mpirun porousSimpleFoam -parallel | tee log logs/log_$(date '+%y-%m-%d_%H_%M_%S')
  p_stop=$(date '+%s.%N')
  p_elapsed=$(bc -l <<< "$p_stop - $p_start")
  echo "Reconstruction started"
  reconstructPar
fi
#decomposePar
#sbatch -n 4
#mpirun -np 4 porousSimpleFoam -parallel | tee log logs/log_$(date '+%y-%m-%d_%X')
#reconstructPar

# One thread version
#runApplication
#porousSimpleFoam | tee log logs/log_$(date '+%y-%m-%d_%X')

stop=$(date '+%s.%N')
elapsed=$(bc -l <<< "$stop - $start")
echo "Run of $destination on $(date '+%y-%m-%d_%H_%M_%S') and $threads threads till $seciteration sec/iteration took $elapsed sec ($p_elapsed); $4" >> ../result_time

# Demo is stopped on this stop for now

# 6. Collect data
# Some paraview scripts
foamToVTK -allPatches

cd ..

# pvpython --force-offscreen-rendering render_foam.py $destination
xvfb-run -a -s "-screen 0 3840x2160x24" pvpython render_foam.py $destination

python3 create_gif.py $destination

echo "All done"
