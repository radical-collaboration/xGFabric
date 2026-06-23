#!/bin/bash
#
# config_template.sh - User Configuration Template
#
# Copy this file to config.sh and fill in your values.
# config.sh is gitignored and should never be committed.
#
# Runs one workflow and exits. 
#
#
# No need to edit values for "old values", as the new makeflow + workqueue makes 
# these portions obsolete.
#
# This file is sourced by main.sh and other scripts

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
MAX_WORK_QUEUE_WORKER_WALLTIME="01:00:00"
WORK_QUEUE_QOS="regular"
WORK_QUEUE_CONSTRAINT="cpu"
WORK_QUEUE_NUM_NODES=72
AWAIT_WORK_QUEUE_WORKERS_TIMEOUT=72000
WORK_QUEUE_PROJECT_NAME="wq_cfdaai"


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

# WOOF endpoint for model storage
SENSPOT_MODELS_ENDPOINT="woof://169.231.229.75/sharedfs/ucsb-data"

# Keep local archives after sending (true) or remove them (false)
SENSPOT_KEEP_ARCHIVES=true








################################################################################
# Old Values (no change needed, but kept so vars are set)
################################################################################

# UCSB SSH
# Machine list for distributed execution (one hostname per line)
MACHINE_LIST="${WORK_DIR}/machine_list.txt"
# SSH key for passwordless access
SSH_KEY="${WORK_DIR}/id_rsa"
# Remote working directory on UCSB machines
UCSB_REMOTE_WORK_DIR="/path/to/remote/intheloop"
# Results Archiving (UCSB only)
# Automatically archive results to storage after pipeline completes (UCSB only)
AUTO_ARCHIVE=true
# ARCHIVE_DIR="/local/foam/cases/archived"

# Hbyrid Mode Config
# NERSC SSH access from UCSB.
# NOTE: Use NERSC_SSH_HOST (not NERSC_HOST) to avoid collision with the
# NERSC_HOST environment variable that NERSC sets automatically on its systems.
NERSC_SSH_HOST="perlmutter.nersc.gov"
NERSC_USER="YOUR_NERSC_USERNAME"
NERSC_SSH_KEY="${WORK_DIR}/nersc"
NERSC_REMOTE_WORK_DIR="/global/homes/X/YOUR_NERSC_USERNAME/intheloop"
NERSC_SCRATCH_DIR="/pscratch/sd/X/YOUR_NERSC_USERNAME"

# RaceLab GPU1 SSH access (rw-gpu1.cs.ucsb.edu) — full-access machine, no queue.
# Run env/setup_racelab.sh once to bootstrap conda + GPU environment before use.
RACELAB_SSH_HOST="rw-gpu1.cs.ucsb.edu"
RACELAB_USER="YOUR_RACELAB_USERNAME"
RACELAB_SSH_KEY="${WORK_DIR}/racelabgpu"
RACELAB_REMOTE_WORK_DIR="/home/YOUR_RACELAB_USERNAME/intheloop_hybrid"

HYBRID_MODULE_PINN="racelab"
HYBRID_MODULE_FNO="racelab"

