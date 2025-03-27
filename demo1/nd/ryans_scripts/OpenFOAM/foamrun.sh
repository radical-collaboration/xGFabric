#!/bin/bash

touch out.log

echo "Task started at [$(date '+%Y-%m-%d %H:%M:%S')]" >> out.log

source ~/.bashrc
conda activate cctools-env

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

# List of files to plot
files=(
  "alpha.water_0"
  "alpha.waterFinalRes_0"
  "alpha.waterIters_0"
  "clockTime_0"
  "contCumulative_0"
  "contCumulative_1"
  "contCumulative_2"
  "contGlobal_0"
  "contGlobal_1"
  "contGlobal_2"
  "contLocal_0"
  "contLocal_1"
  "contLocal_2"
  "CourantMax_0"
  "CourantMax_1"
  "CourantMax_2"
  "CourantMean_0"
  "CourantMean_1"
  "CourantMean_2"
  "executionTime_0"
  "foamLog.awk"
  "p_rgh_0"
  "p_rgh_1"
  "p_rgh_2"
  "p_rghFinalRes_0"
  "p_rghFinalRes_1"
  "p_rghFinalRes_2"
  "p_rghIters_0"
  "p_rghIters_1"
  "p_rghIters_2"
  "pcorr_0"
  "pcorrFinalRes_0"
  "pcorrIters_0"
  "Separator_0"
  "Time_0"
)


# Iterate through the list of files
for file in "${files[@]}"; do
    # Construct the full path to the log file
    log_file="$log_dir/$file"

    # Extract the filename without the directory to use for the output filename
    base_name=$(basename "$log_file")

    # Remove any extensions (like .awk) and use as the base for the plot filename
    plot_base_name="${base_name%.*}"
    output_file="${plot_base_name}.png"

    # Gnuplot commands
  gnuplot_commands=$(cat <<EOF
set terminal png
set output "$output_file"
set title "$plot_base_name"
set xlabel "Time (s)"
set ylabel "Value"
plot "$log_file" u 1:2 w l title "$plot_base_name"
unset output
EOF
)


  # Execute gnuplot and check the exit code
  gnuplot -persist <<EOF_GNUPLOT
$gnuplot_commands
EOF_GNUPLOT
  gnuplot_exit_code=$?

    if [ $gnuplot_exit_code -ne 0 ]; then
        echo "Error encountered while plotting: $log_file (exit code: $gnuplot_exit_code)"
    else
        echo "Plotted: $log_file and saved as $output_file"
    fi
done

echo "Finished plotting all files."

mv *.png ../figures

# foamToVTK -allPatches


cd ..

echo "Task finished at [$(date '+%Y-%m-%d %H:%M:%S')]" >> out.log