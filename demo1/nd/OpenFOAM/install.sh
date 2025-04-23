#!/bin/bash

# activate conda environment
source ~/.bashrc
conda activate cctools-env

# add OpenFOAM module to computer
module add openfoam/10.0/gcc/8.5.0
module add paraview/5.11.2

# check if the directory exists
DIRECTORY=damBreak

if [ -d "$DIRECTORY" ]; then
    echo "$DIRECTORY already exists. Redownloading..."
    rm -rf $DIRECTORY
    cp -r $FOAM_TUTORIALS/multiphase/interFoam/laminar/damBreak/damBreak .
else 
    cp -r $FOAM_TUTORIALS/multiphase/interFoam/laminar/damBreak/damBreak .
fi

DIRECTORY=figures

if [ -d "$DIRECTORY" ]; then
    echo "$DIRECTORY already exists. Removing it..."
    rm $DIRECTORY/*
else 
    mkdir "figures"
fi