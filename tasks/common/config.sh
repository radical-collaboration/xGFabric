#/bin/bash

# ROSE / Python config
INTERIM_DIR=/pscratch/sd/b/bcarter/playground/interim

COMMON_DIR="../common"

# Force a specific system type instead of auto-detection
# Valid values: "nersc", "ucsb", "local", "hybrid"
SYSTEM_TYPE="nersc"
NERSC_PROJECT_ID="m5290"



################################################################################
# Data Source Configuration + Simulation Config
################################################################################

# CSPOT endpoint for sensor data
CSPOT_ENDPOINT="woof://128.111.45.61/davisstations/daviscupsout"

# Alternative: Pre-downloaded data directory (if CSPOT not available)
# DATA_SOURCE_DIR="/path/to/local/sensor/data"

# Number of CSPOT records to fetch (default: 50)
# When combined with DATA_CUTOFF_DATE: fetches up to N records AFTER the cutoff date
# When used alone: fetches the N most recent records
CSPOT_LIMIT="72"

# Cutoff date for sensor data.
# Format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DD
# When set: fetches the N most recent records AT OR BEFORE this date from CSPOT.
# If CSPOT no longer stores data that old, falls back to HISTORICAL_DATA_PATH.
DATA_CUTOFF_DATE="2026-05-28T19:22:30Z"

# Path to archived historical sensor CSVs (Davis station, same format as CSPOT output).
# Used as fallback when DATA_CUTOFF_DATE is set but CSPOT data doesn't reach back that far.
HISTORICAL_DATA_PATH="$SCRATCH/cups_historical"

# Simulation parameter generation mode:
#   "interpolated" - Generate evenly-spaced wind speeds between min/max (default)
#   "sensor_direct" - Use actual wind speeds and directions from sensor data
SIM_PARAM_MODE="sensor_direct"

# Number of simulations (meaning depends on mode):
#   interpolated mode: number of evenly-spaced points to generate
#   sensor_direct mode: maximum number of unique sensor measurements to use
NUM_SIMULATIONS=72
NUM_OF_CORES_PER_SIM=32

################################################################################
# Workqueue and Workflow Configuration 
################################################################################

MAX_PARALLEL_WORKFLOWS=1

# determines how many complete back-to-back workflows you want to run
# be sure to adjust walltime var to reflect number of workflows
MAX_NUMBER_OF_WORKFLOWS=1
TIME_BETWEEN_WORKFLOWS=60
MAX_WORK_QUEUE_WORKER_WALLTIME="02:00:00"
WORK_QUEUE_QOS="regular"
WORK_QUEUE_CONSTRAINT="cpu"
WORK_QUEUE_NUM_NODES=72
AWAIT_WORK_QUEUE_WORKERS_TIMEOUT=72000
WORK_QUEUE_PROJECT_NAME="rose_cfdaai"


################################################################################
# Training Configuration
################################################################################

# Which models to train (space-separated: pcr pinn fno)
TRAIN_MODELS="pcr pinn fno"

################################################################################
# Model Archiving and CSPOT Sending
################################################################################

# Enable/disable automatic model sending via senspot-file-send
SENSPOT_SEND_MODELS=true

# WOOF endpoint for model storage - automatically write to <MODDEL>.nersc.woof
SENSPOT_MODELS_ENDPOINT="woof://169.231.229.75/sharedfs/ucsb-data"

# Keep local archives after sending (true) or remove them (false)
SENSPOT_KEEP_ARCHIVES=true





