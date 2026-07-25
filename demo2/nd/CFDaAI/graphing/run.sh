#!/bin/bash
source ~/miniconda3/etc/profile.d/conda.sh

# activate environment
conda activate cfdaai

# launch the coordinator
python3 graphing.py
