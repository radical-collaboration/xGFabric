#!/bin/bash
#$ -q long
#$ -pe mpi-12 12

# mpi-threads slots

n_slots=12
n_threads=12
seciteration=10
folder_name="cups_structure"

sh cups.sh $folder_name $n_threads $n_slots $seciteration
