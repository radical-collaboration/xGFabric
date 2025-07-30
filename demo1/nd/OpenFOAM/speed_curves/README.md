This directory was used to generate the speedup curves. This was tested only at Notre Dame.

To change from running same number of cores on multiple nodes to different number of cores on a single node, you must uncomment whicever line applies best to your situation in the runme file.
```
# The smp environment is for multi-threaded single node runs (single-node experiments)
# new_line="#!/bin/bash\n#$ -q long\n#$ -pe smp $n_threads\nnodes=$n_nodes\ntotal_cores=$total_cores"

# The long queue is for 64 core machines (multi-node experiments)
# new_line="#!/bin/bash\n#$ -q long\n#$ -pe mpi-$n_threads $total_cores\nnodes=$n_nodes\ntotal_cores=$total_cores"

# The hpc queue is for 48 core machines (multi-node experiments)
# new_line="#!/bin/bash\n#$ -q hpc\n#$ -pe mpi-$n_threads $total_cores\nnodes=$n_nodes\ntotal_cores=$total_cores"
```