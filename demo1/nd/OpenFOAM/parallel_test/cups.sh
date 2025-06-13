if [ -n "$1" ]; then
  folder_name="$1"
fi

if [ -n "$2" ]; then
  threads="$2"
fi

if [ -n "$3" ]; then
  slots="$3"
fi

if [ -n "$4" ]; then
  seciteration="$4"
fi


if ! [ -f cups_structure.zip ]; then
  wget https://notredame.box.com/shared/static/j1nv30fb4vjerbwcc4nqogqi34rdnjj6.zip -O cups_structure.zip
fi


destination="${folder_name}_$(date '+%y-%m-%d_%H_%M_%S')"

start=$(date '+%s.%N')

if conda env list | grep -q "nd-xgfabric"
then
  echo "already created fabric environment"
else
  echo "creating fabric environment"
  conda env create -f ../../environment.yml
fi

if ! [ -d "logs" ]
then
  mkdir "logs"
fi

source ~/.bashrc

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

echo $destination

unzip $folder_name
mv $folder_name $destination


python3 replace.py spare_details/system/decomposeParDict "$destination/system/decomposeParDict" @ $threads
python3 replace.py spare_details/system/controlDict "$destination/system/controlDict" @ $seciteration

folder="$destination"

# Ensure the folder exists
if [ ! -d "$folder" ]; then
    echo "Directory '$folder' does not exist."
    exit 1
fi

# Find all regular files recursively in the folder
find "$folder" -type f | while read -r file; do
    # Check if the file contains 'FoamFile' followed by '{'
    if grep -q 'FoamFile' "$file" && grep -q '{' "$file"; then
        # Check if 'version     2.0;' already exists
        if ! grep -q 'version     2.0;' "$file"; then
            # Use awk to insert the version line after the first '{' following 'FoamFile'
            awk '
            BEGIN {inFoamBlock=0}
            /FoamFile/ {inFoamBlock=1; print; next}
            inFoamBlock && /^\s*{/ {
                print;
                print "version     2.0;";
                inFoamBlock=0;
                next
            }
            {print}
            ' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
            echo "Updated: $file"
        else
            echo "Already has version line: $file"
        fi
    else
        echo "No FoamFile block found: $file"
    fi
done

echo "windspeed winddir $windspeed $winddir"
python3 update.py $windspeed $winddir -f $destination

# 5. Run solver to perform the calculation
cd $destination
# For parallel version (sciped for now)
touch "../logs/$threads_$slots_$destination"

if [ "$threads" -eq 1 ]; then
  porousSimpleFoam | tee "../logs/$threads_$slots_$destination"
else
  decomposePar
  #sbatch -n $threads
  p_start=$(date '+%s.%N')
  mpirun -np $slots porousSimpleFoam -parallel | tee "../logs/$threads_$slots_$destination"
  p_stop=$(date '+%s.%N')
  p_elapsed=$(bc -l <<< "$p_stop - $p_start")
  echo "Reconstruction started"
  reconstructPar
fi

stop=$(date '+%s.%N')
elapsed=$(bc -l <<< "$stop - $start")
echo "Run of $destination on $(date '+%y-%m-%d_%H_%M_%S') and $threads threads till $seciteration sec/iteration took $elapsed sec ($p_elapsed); $4" >> ../result_time


foamToVTK -allPatches

cd ..

pvpython --force-offscreen-rendering render_foam.py $destination
# xvfb-run -a -s "-screen 0 3840x2160x24" pvpython render_foam.py $destination

python3 create_gif.py $destination

echo "All done"