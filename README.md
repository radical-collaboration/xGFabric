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

# install digital twin:

git clone https://github.com/radical-cybertools/digital.twins
cd digital.twins
git checkout release/vanilla-framework
pip install .

# start pubsub broker
cd test/
python3 local_broker.py &

# run
# in this xGFabric repo:

python3 twin.py
```

This runs the entire DT on the RADICAL Tools stack.
