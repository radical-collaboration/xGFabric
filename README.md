# xGFabric

## Overview

The **xGFabric** project seeks to combine advanced network technology, HPC
simulations, and AI surrogate modeling to provide accurate and real-time
inference on-the-edge for digital agricultural applications. 

Specifically:
- It uses a computational-fluid-dynamics simulation to predict wind-field data
- It trains three surrogate models for inference on the edge.

Framework:
- This repository covers the xGFabric's integration with the ROSE framework, an
  active learning framework for producing surrogate models
- Uses the RADICAL Cybertools Suite: AsyncFlow --> Rhapsody --> DragonHPC. 
- This software is meant to be used at NERSC Perlmutter 

## To run:

```bash
dragon rose_app.py
```

This runs the entire workflow. (fetch + sim + train + deploy)

## How to Run on Perlmutter

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-org/pppl-xgfabric.git
   cd pppl-xgfabric
   ```

2. **Create a Conda environment** (the `environment.yml` is in the repo root)

   ```bash
   # for rhap_main
   conda env create -f environment.yml
   
   conda env create -f tasks/do_simulation/environment.yml

   ```


3. **Submit the job** – for testing purposes, the simplest way is to run the Dragon driver directly inside an interactive session.

   ```bash
   salloc --qos interactive --time 02:00:00 --nodes 1 --constraint cpu --account XXX
   
   # Then, inside:
   $ conda activate rhap_main
   $ dragon rose_app.py
   
   ```

> For large-scale batch runs, just create a slurm batch script that does the
> above and activates the conda environemnt. 

## Runtime artifacts
- All artifacts produced by the pipeline are in the `PLAYGROUND_DIR`. See `tasks/common/config.sh`

## Architecture + Layout
Coming soon... but some highlights:

- This contains an abstract Data Communicator for transferring data between
  tasks. It is agnostic to the method of actual data communication (currently
  uses direct and CSPOT)
- All tasks run as executables
- Refactored / cleaned up original sim + training scripts to make it more
  modular
- Every task has its own directory. 

