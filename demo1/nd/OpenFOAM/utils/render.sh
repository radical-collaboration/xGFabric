#!/bin/bash
WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UTILS_DIR="${WORK_DIR}"

destination="$1"
option="$2"
source ~/.bashrc
conda activate xgfabric
echo "Processing results for: $1"

RESULTS_DIR=$destination/results
mkdir -p "$RESULTS_DIR"

if [ "$option" -eq 1 ]; then
    module purge
    module load gcc/11.2.0
    module load openmpi/4.0.6
    module load openfoam/8-20210316
    source $FOAM_ETC/bashrc
    module load paraview/5.10.1
    pvpython --force-offscreen-rendering "$UTILS_DIR/render_foam.py" "$destination"

elif [ "$option" -eq 2 ]; then
    module purge
    module add openfoam/10.0/gcc/8.5.0 > /dev/null 2>&1
    module add paraview/5.11.2
    pvpython --force-offscreen-rendering "$UTILS_DIR/render_foam.py" "$destination"
    #xvfb-run -a -s "-screen 0 3840x2160x24" pvpython "$UTILS_DIR/render_foam.py" "$destination"

elif [ "$option" -eq 3 ]; then
    # ibrun -n 2 pvbatch --force-offscreen-rendering "$UTILS_DIR/render_foam.py" "$destination"
    echo -e "#!/bin/bash\nsource ~/.bashrc\nconda activate xgfabric\nmodule purge\nmodule load intel/23.1 impi/21.9 openfoam/8 paraview-osmesa/5.12.0\npvbatch --force-offscreen-rendering --mesa "$UTILS_DIR/render_foam.py" "$destination"" > stampede3_png.sh

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
    rm "$output_file"

elif [ "$option" -eq 4 ]; then
    pvpython --force-offscreen-rendering "$UTILS_DIR/render_foam.py" "$destination"
fi

echo "Script completed successfully!"
echo "Check png_outputs directory for visualization outputs"

# Find latest time directory
# LATEST_TIME=$(ls -d [0-9]* 2>/dev/null | sort -n | tail -1)
# if [ -z "$LATEST_TIME" ]; then
#     echo "Warning: No time directories found"
# else
#     echo "Latest time: $LATEST_TIME"

#     # Convert to VTK
#     echo "Converting to VTK..."
#     mkdir -p VTK
#     foamToVTK -time "$LATEST_TIME" >> log 2>&1 || echo "Warning: foamToVTK failed"
# -latestTime
# fi

# Create results directory in work directory


# Crop images
echo "Cropping images..."
if [ -d "$destination/png_outputs" ] && [ -n "$(ls -A "$destination/png_outputs" 2>/dev/null)" ]; then
    python "$UTILS_DIR/crop_image.py" "$destination"
fi

# Move images to results directory if they exist
if [ -d "$destination/png_outputs" ] && [ -n "$(ls -A "$destination/png_outputs" 2>/dev/null)" ]; then
    echo "Moving images to results directory..."
    mv "$destination/png_outputs" "$RESULTS_DIR/images" 2>/dev/null || echo "Warning: Failed to move images"
fi

# move cropped images up a directory and remove uncropped images
mv $RESULTS_DIR/images/cropped/* $RESULTS_DIR/
rm -rf $RESULTS_DIR/images
rm -rf $RESULTS_DIR/cropped

num_images=$(ls $RESULTS_DIR | wc -l)
# Create GIF from PNGs in results directory
if [ "$num_images" -gt 1 ]; then
    echo "Creating GIF..."
    python3 "$UTILS_DIR/create_gif.py" "$RESULTS_DIR" "$RESULTS_DIR/${destination}.gif"
else
    echo "Warning: Not enough images for GIF creation"
fi

mv "$RESULTS_DIR" "$(dirname "$RESULTS_DIR")/.."

# # Move VTK data to results if it exists (before cleanup)
# if [ -d "$destination/VTK" ]; then
#     mv "$destination/VTK" "$RESULTS_DIR/" 2>/dev/null || echo "Warning: Failed to move VTK"
# fi

# # Delete case directory - ALWAYS DO THIS
# echo "Deleting case directory: $destination"
# if rm -rf "$destination"; then
#     echo "Case directory deleted successfully"
# else
#     echo "ERROR: Failed to delete case directory!"
#     exit 1
# fi

# Clean up VTK data after GIF is created
if [ -d "$RESULTS_DIR/VTK" ]; then
    echo "Cleaning up VTK directory..."
    rm -rf "$RESULTS_DIR/VTK" || echo "Warning: Failed to clean VTK"
fi

echo "Results saved to $(dirname "$RESULTS_DIR")/.."
