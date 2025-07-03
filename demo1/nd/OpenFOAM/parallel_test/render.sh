#!/bin/bash
HERE=`pwd`
destination="$HERE/$1"
option="$2"
source ~/.bashrc
conda activate xgfabric

if [ "$option" -eq 1 ]; then
    module purge
    module load gcc/11.2.0
    module load openmpi/4.0.6
    module load openfoam/8-20210316
    source $FOAM_ETC/bashrc
    module load paraview/5.10.1
    pvpython --force-offscreen-rendering render_foam.py $destination

elif [ "$option" -eq 2 ]; then
    module purge
    module add openfoam/10.0/gcc/8.5.0 > /dev/null 2>&1
    module add paraview/5.11.2
    pvpython --force-offscreen-rendering render_foam.py $destination
    #xvfb-run -a -s "-screen 0 3840x2160x24" pvpython render_foam.py $destination

elif [ "$option" -eq 3 ]; then
    # ibrun -n 2 pvbatch --force-offscreen-rendering render_foam.py $destination
    echo -e "#!/bin/bash\nsource ~/.bashrc\nconda activate xgfabric\nmodule purge\nmodule load intel/23.1 impi/21.9 openfoam/8 paraview-osmesa/5.12.0\npvbatch --force-offscreen-rendering --mesa render_foam.py $destination" > stampede3_png.sh

    job_id=$(sbatch --time="24:0:0" --nodes="1" --partition="skx" --ntasks="1" --mem="16GB" --parsable --output="pngs_%j.out" stampede3_png.sh | tail -n 1)

    echo "Submitted job: $job_id"

    output_file="pngs_${job_id}.out"

    # Wait for output file to be created
    while [[ ! -f "$output_file" ]]; do
        sleep 5
    done

    # Monitor output in real-time
    echo "=== Real-time Job Output ==="
    tail -f "$output_file" &
    tail_pid=$!

    # Wait for job completion
    while squeue -j $job_id 2>/dev/null | grep -q $job_id; do
        sleep 10
    done

    # Stop tailing and show final status
    kill $tail_pid 2>/dev/null
    echo "Job $job_id completed"

    rm stampede3_png.sh

fi

python3 create_gif.py $destination

echo "Script completed successfully!"
echo "Check png_outputs directory for visualization outputs"