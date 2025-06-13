#!/bin/bash

echo -n "This script has been tested on the following clusters:
1. Purdue ANVIL
2. Notre Dame
3. Texas Stampede3

==> Which cluster are you running on? (1-3)
==> "

read cluster_choice

case $cluster_choice in
    1)
        echo "==> You selected: Purdue ANVIL"
        module load gcc/11.2.0
        module load openmpi/4.0.6
        module load openfoam/8-20210316
        source $FOAM_ETC/bashrc
        module load paraview/5.10.1
        ;;
    2)
        echo "==> You selected: Notre Dame"
        module add openfoam/10.0/gcc/8.5.0
        module add paraview/5.11.2
        ;;
    3)
        echo "==> You selected: Texas Stampede3"
        ;;
    *)
        echo "Invalid selection. Please choose 1, 2, or 3."
        exit 1
        ;;
esac

n_slots=5
n_threads=5
seciteration=2
folder_name="cups_structure"

sh cups.sh $folder_name $n_threads $n_slots $seciteration