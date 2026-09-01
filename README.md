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

```bash

# switch to the branch of this README.

# Install the PySPOT submodule
git submodule init
git submodule update
# install CSPOT already if not done (would be done on broker too)
pushd tasks/common/pyspot
bash install_cspot_bin.sh
popd



# install digital twin:
cd ../ # outside of repo

git clone https://github.com/radical-cybertools/digital.twins
cd digital.twins
git checkout release/vanilla-framework
pip install .

cd ../xGFabric # back to the repo

# Edit CONFIG.
#  Pay special attention to DT_STREAM_PUB_ADDR, DT_STREAM_SUB_ADDR, PLAYGROUND_DIR, CUPS_STRUCTURE_ZIP.

# If you don't already have the cups structure ZIP, download here:
wget https://codingcando.com/research/cups_structure.zip

# Simulations are currently being skipped and run by the file system. 
# See `tasks/do_simulation/main.py - tk_do_simulation()` Comment out the three lines to run the full simulation. 
#
# Real sensor data is only emitted once every 5 minutes. So, the davis sensor emits fake data every 5 seconds for testing. See `tasks/davis.py`.


# start pubsub broker
cd test/
python3 local_broker.py &

# run
# in this xGFabric repo:

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


