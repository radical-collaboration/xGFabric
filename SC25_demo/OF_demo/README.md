# OpenFOAM Simulation - OF_demo

Simple workflow for running OpenFOAM simulations with custom windspeed parameters and automatic result processing.

## Directory Structure

```
OF_demo/
├── main.sh                      # Main entry point
├── cups_structure.zip           # Input simulation template
├── README.md                    # This file
└── utils/                       # Utility scripts
    ├── OF_simulation.sh         # Runs in compute node
    ├── process_results.sh       # Post-processing
    ├── set_windspeed.py         # Sets inlet velocity
    ├── replace.py               # Updates config files
    ├── create_gif.py            # GIF creation
    ├── render_foam.py           # ParaView visualization
    ├── vtk_to_csv.py            # Data export
    └── monitor_job.sh           # Manual monitoring (optional)
```

When you run `./main.sh`, it creates:
- `cups_structure_ws<X>_<Y>_<Z>_<timestamp>/` - Temporary simulation case (deleted after processing)
- `results/cups_structure_ws<X>_<Y>_<Z>_<timestamp>/` - Final results (images + GIF)

## Quick Start

```bash
# Run with defaults (cups_structure.zip, 32 threads, 5 m/s windspeed)
./main.sh

# Or customize parameters
./main.sh cups_structure.zip 16 2.5 0.0 0.0
```

## Usage

```bash
./main.sh [<zip-file> <threads> <x_windspeed> [y_windspeed] [z_windspeed]]
```

### Parameters (All Optional)

- **zip-file**: Input zip file (default: `cups_structure.zip`)
- **threads**: Number of parallel threads (default: `32`)
- **x_windspeed**: Wind speed X component (m/s) (default: `5`)
- **y_windspeed**: Wind speed Y component (m/s) (default: `0.0`)
- **z_windspeed**: Wind speed Z component (m/s) (default: `0.0`)

### Examples

```bash
# Run with all defaults
./main.sh

# 16 threads, custom windspeed
./main.sh cups_structure.zip 16 2.5

# 3D windspeed components
./main.sh cups_structure.zip 32 3.0 0.5 0.2
```

## Complete Workflow

**main.sh** handles the entire pipeline:

1. **Setup** - Extracts zip, sets windspeed, configures threads
2. **Submit** - Submits job to queue via qsub
3. **Monitor** - Waits for job completion (polls qstat)
4. **Process** - Automatically runs result export and GIF creation

### Detailed Steps

1. **main.sh** - Entry point
   - Validates inputs
   - Extracts zip file
   - Sets windspeed parameters (x, y, z)
   - Configures parallel decomposition
   - Submits job to queue via qsub
   - Monitors job until completion
   - Triggers result processing

2. **OF_simulation.sh** - Runs in compute node (qsub)
   - Loads OpenFOAM environment
   - Decomposes domain for parallel processing
   - Runs porousSimpleFoam with MPI
   - Reconstructs results

3. **process_results.sh** - Post-processing
   - Converts simulation results to VTK
   - Converts VTK to CSV data
   - Creates visualizations with ParaView
   - Generates animated GIF

## Output

Results are created in the same directory as main.sh:

```
results/cups_structure_ws2.5_0.0_0.0_25-07-21_01_54_23/
├── images/                                               # Visualization frames
│   ├── frame_0000.png
│   ├── frame_0001.png
│   └── ...
└── cups_structure_ws2.5_0.0_0.0_25-07-21_01_54_23.gif   # Animated GIF
```

**Note:** Both the original case directory and intermediate VTK files are deleted after processing to save disk space. Only the final images and GIF are preserved.

## Environment

Requires:
- OpenFOAM/10.0 (loaded on compute nodes)
- SGE job scheduler (qsub)
- Python 3 with: `meshio`, `pandas`, `pillow`
- `bc` utility for calculations
- ParaView (optional, for visualization and GIF creation)

## Manual Post-Processing

To reprocess results from an existing case:

```bash
./process_results.sh <case_directory>
```

