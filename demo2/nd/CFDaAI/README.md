# CFDaAI In-the-Loop System

Unified CFD simulation and ML training pipeline that works across:
- **NERSC Perlmutter** (SLURM-based scheduling)
- **Notre Dame CRC** (UGE-based scheduling)
- **UCSB Cluster** (SSH-based distributed execution)
- **Local systems** (sequential execution)

## Quick Start

```bash
# 1. Edit configuration
cp config.sh.example config.sh  # if needed
vim config.sh

# 2. Run pipeline (auto-detects system)
./main.sh

# 3. Run with options
./main.sh --mode sim-only    # Only run simulations
./main.sh --mode train-only  # Only train models
./main.sh --dry-run          # Show what would run
```

## Directory Structure

```
intheloop/
├── main.sh                 # Entry point
├── config.sh               # User configuration
│
├── env/                    # Environment management
│   ├── system_config.sh    # System detection & init
│   ├── env_nersc.sh        # NERSC module/conda setup
│   └── env_ucsb.sh         # UCSB environment setup
│
├── lib/                    # Shared libraries
│   ├── common.sh           # Logging, timing, utilities
│   ├── dispatch.sh         # Task dispatcher (SLURM/SSH/local)
│   └── simulations.sh      # Simulation orchestration
│
├── data/                   # Data management
│   └── data_source.sh      # CSPOT fetching, data validation
│
├── tasks/                  # Portable task wrappers
│   └── simulation_task.sh  # Single simulation execution
│
├── slurm/                  # SLURM job templates (NERSC)
│   ├── simulation_slurm.sh # Simulation job array
│   └── pcr_train_slurm.sh  # PCR training job
│
├── training/               # ML training orchestration
│   ├── orchestrate_training.sh  # Training dispatcher
│   ├── pcr/                # PCR model training
│   ├── pinn/               # PINN model training
│   └── fno/                # FNO model training
│
├── simulation/             # OpenFOAM simulation core
│   ├── runme.sh            # Core simulation script
│   ├── process_results.sh  # Result processing
│   └── template/           # OpenFOAM case template
│
├── utils/                  # Utilities
│   ├── environment.yml     # Conda environment spec
│   └── senspot-get         # CSPOT data fetcher
│
├── _dump/                  # Original scripts (reference)
│   ├── main.sh             # Original orchestrator
│   ├── run_simulations_parallel.sh
│   ├── train_pcr_parallel.sh
│   └── ...
│
├── logs/
│   └── run_<date>/
│       ├── coordinator/
│       │   └── workflow_status_log.csv
│       │
│       └── workflows/
│           └── workflow_<id>/
│               ├── simulations/
│               └── training/
└── results/
    └── run_<date>/
        └── workflow_<id>
            ├── data/
            ├── params/
            └── simulations/
```

## System Detection

The system is auto-detected based on:
- **NERSC**: `$NERSC_HOST` environment variable
- **UCSB**: Presence of `machine_list.txt` and SSH key
- **Local**: Fallback for development/testing

Override with: `./main.sh --system nersc`

## Configuration

Edit `config.sh` to customize:

```bash
# Data source
CSPOT_ENDPOINT="woof://128.111.45.61/davisstations/daviscupsout"

# Models to train
TRAIN_MODELS="pcr pinn fno"

# UCSB machines (one per line in machine_list.txt)
MACHINE_LIST="${WORK_DIR}/machine_list.txt"

# SLURM settings
SIM_SLURM_QOS="regular"
SIM_SLURM_TIME="01:00:00"
```

## Execution Modes

### Full Pipeline
```bash
./main.sh --mode full
```
Runs complete loop: data → simulations → training → evaluation

### Simulations Only
```bash
./main.sh --mode sim-only
```
Fetches data and runs CFD simulations

### Training Only
```bash
./main.sh --mode train-only
```
Uses existing simulation results to train models

## How It Works

### NERSC (SLURM)
1. Submits simulations as SLURM job array
2. Waits for completion via job dependencies
3. Submits training jobs (PCR array, PINN/FNO single GPU)
4. Results collected to shared filesystem

### UCSB (SSH)
1. Distributes simulations across machines via SSH
2. Parallel execution with load balancing
3. Collects results to head node
4. Distributed PCR training across machines

### Local
1. Sequential simulation execution
2. Sequential training
3. Useful for testing/development

## Adding New Features

### New Model Type
1. Create `training/<model>/train_<model>.py`
2. Add SLURM template: `slurm/<model>_train_slurm.sh`
3. Add case to `training/orchestrate_training.sh`
4. Update `TRAIN_MODELS` in config

### New Task Type
1. Create portable wrapper in `tasks/`
2. Add SLURM template in `slurm/`
3. Add orchestration function in `lib/`

## Troubleshooting

### Check system detection
```bash
source env/system_config.sh
init_system
echo "System: $SYSTEM_TYPE"
echo "Features: GPU=$HAS_GPU CSPOT=$HAS_CSPOT MACHINES=$HAS_MACHINES"
```

### Dry run
```bash
./main.sh --dry-run
```

### NERSC job status
```bash
squeue -u $USER
```
