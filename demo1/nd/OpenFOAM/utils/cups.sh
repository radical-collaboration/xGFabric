source ~/.bashrc
conda activate xgfabric


if [ "$cluster" -eq 1 ]; then
    module --force purge
    module load gcc/11.2.0
    module load openmpi/4.0.6
    module load openfoam/8-20210316
    source $FOAM_ETC/bashrc
    module load paraview/5.10.1
elif [ "$cluster" -eq 2 ]; then
    module --force purge
    module add openfoam/10.0/gcc/11.5.0 > /dev/null 2>&1
    module add paraview/5.11.2
elif [ "$cluster" -eq 3 ]; then
    module --force purge
    module load intel/23.1 impi/21.9 openfoam/8 paraview/5.12.0
    export LD_LIBRARY_PATH=/opt/intel/oneapi/mpi/2021.11/lib:$LD_LIBRARY_PATH
elif [ "$cluster" -eq 4 ]; then
    module load spack
    . /global/common/software/nersc9/spack/1.1.0/share/spack/setup-env.sh
    module load conda
    module load paraview || true  # paraview may not be needed at runtime
    spack load openmpi@4.1.5
    group_num=$(groups | awk -F" " '{print $2}')
    export OPENFOAM_ROOT="/global/common/software/$group_num/openfoam"
    source "$OPENFOAM_ROOT/OpenFOAM-dev/etc/bashrc" || true  # non-fatal: OF env may already be set
    export LD_LIBRARY_PATH=$(spack location -i openmpi@4.1.5)/lib:$LD_LIBRARY_PATH

    if ! command -v icoFoam -help &> /dev/null; then
        echo "OpenFOAM is not available."
        if spack find | grep openfoam &> /dev/null; then
            echo "OpenFOAM found..."
            echo "Adding OpenFOAM to PATH"
        else
            echo "OpenFOAM was not found."
            printf "Do you wish to compile OpenFOAM from scratch? This could take upwards of 2 hours. [y]/n\n==> "
            read compile
            compile="${compile,,}"
            if [[ "$compile" == "" ]]; then
                compile="yes"
            fi

            case $compile in
                y|yes)
                    echo "Compiling..."
                    ;;
                n|no)
                    echo "Exiting..."
                    exit 0
                    ;;
                *)
                    echo "Unknown option: $compile"
                    echo "Exiting..."
                    exit 1
                    ;;
            esac
            module load gcc
            module load cmake
            spack install openmpi@4.1.5
            spack load openmpi@4.1.5
            export OPENFOAM_ROOT="/global/common/software/$group_num/openfoam"
            mkdir -p $OPENFOAM_ROOT
            cd $OPENFOAM_ROOT
            git clone https://github.com/OpenFOAM/OpenFOAM-dev.git -b version-11
            git clone https://github.com/OpenFOAM/ThirdParty-dev.git -b version-11
            cd $OPENFOAM_ROOT/ThirdParty-dev
            ./Allwmake -j
            cd $OPENFOAM_ROOT/OpenFOAM-dev
            ./Allwmake -j
            source $OPENFOAM_ROOT/OpenFOAM-dev/etc/bashrc
        fi
        spack load openfoam
    fi   
fi

ZIP_FILE="$UTILS_DIR/cups_structure.zip"
if ! [ -f "$ZIP_FILE" ]; then
    wget https://notredame.box.com/shared/static/j1nv30fb4vjerbwcc4nqogqi34rdnjj6.zip -O "$ZIP_FILE"
fi

echo "========================================"
echo "OpenFOAM Simulation Started"
echo "========================================"
start=$(date '+%s.%N')

# 3. Load most recent online data
b=$(senspot-get -W woof://169.231.230.76/sharedfs/unl-data/daviscupsout)
vals=$(awk -F" " '{print $1}' <<< "$b")
WIND_SPEED=$(awk -F":" '{print $4}' <<< "$vals")
WIND_DIR=$(awk -F":" '{print $7}' <<< "$vals")

if [ -z "$WIND_SPEED" ]; then
    WIND_SPEED="5"
fi

if [ -z "$WIND_DIR" ]; then
    WIND_DIR="NW"
fi

echo "================================================"
echo "OpenFOAM Simulation Setup"
echo "================================================"
echo "Case:      $destination"
echo "Threads:   $threads"
echo "WIND_SPEED: $WIND_SPEED m/s"
echo "Wind direction: $WIND_DIR"
echo "================================================"

unzip -q $ZIP_FILE -d $destination
echo "Extracting case..."
if [ -d "$destination/cups_structure" ]; then
    mv "$destination/cups_structure"/* "$destination"/ 2>/dev/null || true
    rmdir "$destination/cups_structure" 2>/dev/null || true
fi

# Step 2: Set wind speed
echo "Setting wind speed to $WIND_SPEED..."
python3 $UTILS_DIR/set_windspeed.py $destination $WIND_SPEED $WIND_DIR

# Step 3: Configure parallel decomposition
echo "Configuring for $threads threads..."
python3 "$UTILS_DIR/replace.py" "$UTILS_DIR/spare_details/system/decomposeParDict" "$destination/system/decomposeParDict" @ "$threads"
python3 "$UTILS_DIR/replace.py" "$UTILS_DIR/spare_details/system/controlDict" "$destination/system/controlDict" @ "$seciteration"

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

# 5. Run solver to perform the calculation
cd $destination


if [ "$threads" -eq 1 ]; then
    p_start=$(date '+%s.%N')
    porousSimpleFoam
    p_stop=$(date '+%s.%N')
    p_elapsed=$(bc -l <<< "$p_stop - $p_start")
else
    decomposePar -fileHandler uncollated -force    
    p_start=$(date '+%s.%N')
    
    mpirun -n $threads porousSimpleFoam -parallel

    p_stop=$(date '+%s.%N')
    p_elapsed=$(bc -l <<< "$p_stop - $p_start")
    
    echo "Reconstruction started"
    reconstructPar
fi

stop=$(date '+%s.%N')
elapsed=$(bc -l <<< "$stop - $start")
echo "========================================"
echo "Completed in $elapsed seconds"
echo "Finished: $(date)"
echo "========================================"
echo "Run of $destination on $(date '+%y-%m-%d_%H_%M_%S') and $threads threads till $seciteration sec/iteration took $elapsed sec ($p_elapsed);" >> ../../result_time

if [[ "$render" == "true" ]]; then
    echo "========================================"
    echo "Creating VTK outputs"
    echo "========================================"
    foamToVTK -latestTime
fi

cd ..
