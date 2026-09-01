# xGFabric - Implemented using the Digital Twin Abstraction Framework

## Overview

The **xGFabric** project seeks to combine advanced network technology, HPC
simulations, and AI surrogate modeling to provide accurate and real-time
inference on-the-edge for digital agricultural applications. 

Specifically:
- It uses a computational-fluid-dynamics simulation to predict wind-field data
- It trains three surrogate models for inference on the edge.

Framework:
- This repository covers the xGFabric expressed as a digital twin.
- The DT consists of a sensor utility task, a sink utility task, and a WindField agent.
- The WindField agent is composed of multiple investigators:
- - PCR
- - PINN
- - FNO

## To run:

1. Install prereq's -- conda

The `cfdaai` and `xgfabric` conda environment is required. A compute node should
be able to activate these. These environments are saved in
`/global/common/software/m5290/bcarter/mconda/envs/cfdaai` and
`/global/common/software/m5290/bcarter/mconda/envs/xgfabric`.


2. Install PySPOT as a submodule on Perlmutter

In root of repository:
`git submodule init`
`git submodule update`
`pushd tasks/common/pyspot`
`bash install_cspot_bin.sh`
`popd`

3. Install the digital twin in its own location.

git clone https://github.com/radical-cybertools/digital.twins
cd digital.twins
git checkout devel
pip install .

4. Back to the xGFabric repo, edit configs.

Pay attention to the following:
- `DT_STREAM_PUB_ADDR` and `DT_STREAM_SUB_ADDR` which is the publish address for the ZMQ stream pubsub
  backend

- `PLAYGROUND_DIR` where all artifacts will go. Recommend the pscratch file
  system.

- `CUPS_STRUCTURE_ZIP` where the CUPS structure description goes. If you don't
  have the zip, use the one available at: ``

- `NODE_COUNT` - number of nodes to run on (specific when running on Dragon)

- `SIM_THREADS` and `NUM_OF_CORES_PER_SIM`. These should match. The number of
  cores used for a sim. Recommended to be 32 cores

- `CSPOT_LIMIT` and `NUM_SIMULATIONS`. Currently, these should also match. This
  is the number of cspot readings to batch and then simulate. Note: if running
  on interactive QOS, and since each sim takes 32 cores, it's not recommended to
  fetch/run more than 32 values and sims. (To run the full 72, use a regular
  sbatch)



5. Notes on run:

**Simulations are currently being skipped and run by the file system.**

See `tasks/do_simulation/main.py - tk_do_simulation()` Uncomment out the three
lines to simply return pre-run simulations. 

**Real sensor data is only emitted once every 5 minutes.**
So, the davis sensor emits fake data every 5 seconds for testing. See `tasks/davis.py`.

6. Start:
Start the ZMQ Broker:
```
python3 local_broker.py
```

7. Run:
```
python3 twin.py
```
This runs the entire DT on the RADICAL Tools stack.


## DT Graph:

```
wind sensor --->  wind field ---> sink
Persist Util.      Agent           Util. Task
                     w
                 3 Invest. 
                 /   |    \
              FNO   PCR   PINN

                Same agent as 
                 above sends
                surrogates to 
                  profiler
            |                 ^
            V                 |
        Base Profiler --> Pi Profiler 
```

Everything runs at the moment on Perlmutter. Soon this will be extended to have
a Pi act as a inference backend, and Perlmutter to act as the learning + sim
backend. 


