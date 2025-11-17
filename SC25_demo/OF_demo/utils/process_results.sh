#!/bin/bash

################################################################################
# Process Results - Export to CSV and create GIF
# Usage: ./process_results.sh <case_directory> <work_directory>
################################################################################

[ "$#" -lt 2 ] && { echo "Usage: $0 <case_directory> <work_directory>"; exit 1; }

CASE_DIR="$1"
WORK_DIR="$2"
CASE_NAME=$(basename "$CASE_DIR")
HERE=$(pwd)
UTILS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ -d "$CASE_DIR" ] || { echo "Error: Case directory not found"; exit 1; }

echo "Processing results for: $CASE_NAME"

# Load OpenFOAM environment
source ~/.bashrc 2>/dev/null || true
module purge 2>/dev/null || true
module add openfoam/10.0/gcc/8.5.0 2>/dev/null || true
module add paraview/5.11.2 2>/dev/null || true
conda activate xgfabric 2>/dev/null || true

cd "$CASE_DIR" || { echo "Error: Cannot cd to case directory"; exit 1; }

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

# Convert VTK to CSV
cd "$HERE" || exit 1
echo "Converting to CSV..."
python3 "$UTILS_DIR/vtk_to_csv.py" "$CASE_DIR" 10 2>/dev/null || echo "Warning: vtk_to_csv.py failed"

# Create results directory in work directory
RESULTS_DIR="${WORK_DIR}/results/${CASE_NAME}"
mkdir -p "$RESULTS_DIR"

# Create visualizations
# echo "Creating visualizations..."
# if command -v pvpython &>/dev/null || command -v pvbatch &>/dev/null; then
#     pvpython --force-offscreen-rendering "$UTILS_DIR/render_foam.py" "$CASE_DIR" 2>/dev/null || \
#     pvbatch --force-offscreen-rendering --mesa "$UTILS_DIR/render_foam.py" "$CASE_DIR" 2>/dev/null || \
#     echo "Warning: ParaView visualization failed"
# else
#     echo "Warning: ParaView not available for visualization"
# fi

# Crop images
echo "Cropping images..."
if [ -d "$CASE_DIR/png_outputs" ] && [ -n "$(ls -A "$CASE_DIR/png_outputs" 2>/dev/null)" ]; then
    python "$UTILS_DIR/crop_image.py" "$CASE_DIR"
fi

# Move images to results directory if they exist
if [ -d "$CASE_DIR/png_outputs" ] && [ -n "$(ls -A "$CASE_DIR/png_outputs" 2>/dev/null)" ]; then
    echo "Moving images to results directory..."
    mv "$CASE_DIR/png_outputs" "$RESULTS_DIR/images" 2>/dev/null || echo "Warning: Failed to move images"
fi

# Create GIF from PNGs in results directory
if [ -d "$RESULTS_DIR/images" ] && [ -n "$(ls -A "$RESULTS_DIR/images" 2>/dev/null)" ]; then
    echo "Creating GIF..."
    python3 "$UTILS_DIR/create_gif.py" "$RESULTS_DIR/images" "$RESULTS_DIR/${CASE_NAME}.gif"
    python3 "$UTILS_DIR/create_gif.py" "$RESULTS_DIR/images/cropped" "$RESULTS_DIR/${CASE_NAME}_cropped.gif"
else
    echo "Warning: No images found for GIF creation"
fi

# Move VTK data to results if it exists (before cleanup)
if [ -d "$CASE_DIR/VTK" ]; then
    mv "$CASE_DIR/VTK" "$RESULTS_DIR/" 2>/dev/null || echo "Warning: Failed to move VTK"
fi

# Delete case directory - ALWAYS DO THIS
echo "Deleting case directory: $CASE_DIR"
if rm -rf "$CASE_DIR"; then
    echo "Case directory deleted successfully"
else
    echo "ERROR: Failed to delete case directory!"
    exit 1
fi

# Clean up VTK data after GIF is created
if [ -d "$RESULTS_DIR/VTK" ]; then
    echo "Cleaning up VTK directory..."
    rm -rf "$RESULTS_DIR/VTK" || echo "Warning: Failed to clean VTK"
fi

echo "Done: $CASE_NAME"
echo "Results saved to: $RESULTS_DIR"
