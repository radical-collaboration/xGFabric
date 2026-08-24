#!/bin/bash
#
# config_template.sh - User Configuration Template
#
# Copy this file to config.sh and fill in your values.
# config.sh is gitignored and should never be committed.
#
# cp config_template.sh config.sh
#
# This file is sourced by main.sh and other scripts.

################################################################################
# System Override (optional)
################################################################################

# Force a specific system type instead of auto-detection
# Valid values: "nersc", "ucsb", "local", "hybrid"
# SYSTEM_TYPE="nersc"

################################################################################
# Data Source Configuration
################################################################################

# CSPOT endpoint for sensor data
CSPOT_ENDPOINT="woof://YOUR_CSPOT_HOST/davisstations/daviscupsout"

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
DATA_CUTOFF_DATE="YYYY-MM-DDTHH:MM:SSZ"

# Path to archived historical sensor CSVs (Davis station, same format as CSPOT output).
# Used as fallback when DATA_CUTOFF_DATE is set but CSPOT data doesn't reach back that far.
HISTORICAL_DATA_PATH="/path/to/cups_historical"

################################################################################
# Simulation Configuration
################################################################################

# OpenFOAM template directory
# SIM_TEMPLATE="${WORK_DIR}/simulation/template"

# Maximum number of parallel simulations (UCSB mode)
MAX_PARALLEL_SIMS=72

# Simulation parameter generation mode:
#   "interpolated" - Generate evenly-spaced wind speeds between min/max (default)
#   "sensor_direct" - Use actual wind speeds and directions from sensor data
SIM_PARAM_MODE="sensor_direct"

# Number of simulations (meaning depends on mode):
#   interpolated mode: number of evenly-spaced points to generate
#   sensor_direct mode: maximum number of unique sensor measurements to use
NUM_SIMULATIONS=72

# NERSC SLURM settings for simulations
SIM_SLURM_QOS="regular"
SIM_SLURM_CONSTRAINT="cpu"
SIM_SLURM_TIME="01:00:00"
SIM_SLURM_NODES=1

################################################################################
# Training Configuration
################################################################################

# Which models to train (space-separated: pcr pinn fno)
TRAIN_MODELS="pcr pinn fno"

# PCR grid configuration
PCR_GRID_CONFIG="${WORK_DIR}/training/pcr/grid_config.json"

# NERSC SLURM settings for training
TRAIN_SLURM_QOS="regular"
TRAIN_SLURM_TIME_PCR="00:05:00"
TRAIN_SLURM_TIME_PINN="00:15:00"
TRAIN_SLURM_TIME_FNO="00:15:00"

################################################################################
# UCSB SSH Configuration
################################################################################

# Machine list for distributed execution (one hostname per line)
MACHINE_LIST="${WORK_DIR}/machine_list.txt"

# SSH key for passwordless access
SSH_KEY="${WORK_DIR}/id_rsa"

# Remote working directory on UCSB machines
UCSB_REMOTE_WORK_DIR="/path/to/remote/intheloop"

################################################################################
# Output Configuration
################################################################################

# Keep intermediate files after completion
KEEP_INTERMEDIATE=false

################################################################################
# Model Archiving and CSPOT Sending
################################################################################

# Enable/disable automatic model sending via senspot-file-send
SENSPOT_SEND_MODELS=true

# WOOF endpoint for model storage
SENSPOT_MODELS_ENDPOINT="woof://YOUR_SENSPOT_HOST/sharedfs/models"

# Woof channel suffix appended to model name: <model>.<suffix>.woof
# Use "nersc2" when sending from NERSC, "sb" when sending from UCSB/racelab.
# This lets the receiver distinguish the origin site.
SENSPOT_WOOF_SUFFIX="nersc2"

# Keep local archives after sending (true) or remove them (false)
SENSPOT_KEEP_ARCHIVES=false

################################################################################
# Results Archiving (UCSB only)
################################################################################

# Automatically archive results to storage after pipeline completes (UCSB only)
AUTO_ARCHIVE=true

# Archive destination base directory (defaults to ARCHIVE_BASE from system_config)
# ARCHIVE_DIR="/local/foam/cases/archived"

################################################################################
# Notification (optional)
################################################################################

# Email for job notifications (NERSC)
# SLURM_EMAIL="user@example.com"

# Slack webhook for notifications (optional)
# SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."

################################################################################
# Hybrid Mode Configuration
################################################################################

# NERSC SSH access from UCSB.
# NOTE: Use NERSC_SSH_HOST (not NERSC_HOST) to avoid collision with the
# NERSC_HOST environment variable that NERSC sets automatically on its systems.
NERSC_SSH_HOST="perlmutter.nersc.gov"
NERSC_USER="YOUR_NERSC_USERNAME"
NERSC_SSH_KEY="${WORK_DIR}/nersc"
NERSC_REMOTE_WORK_DIR="/global/homes/X/YOUR_NERSC_USERNAME/intheloop"
NERSC_SCRATCH_DIR="/pscratch/sd/X/YOUR_NERSC_USERNAME"
NERSC_LOGS_DIR="/global/homes/X/YOUR_NERSC_USERNAME/jobs_logs"
# Read-only system installation containing training Python scripts
NERSC_TRAIN_WORK_DIR="/global/homes/X/YOUR_NERSC_USERNAME/common/kurl_system/intheloop"

# RaceLab GPU1 SSH access (rw-gpu1.cs.ucsb.edu) — full-access machine, no queue.
# Run env/setup_racelab.sh once to bootstrap conda + GPU environment before use.
RACELAB_SSH_HOST="rw-gpu1.cs.ucsb.edu"
RACELAB_USER="YOUR_RACELAB_USERNAME"
RACELAB_SSH_KEY="${WORK_DIR}/racelabgpu"
RACELAB_REMOTE_WORK_DIR="/home/YOUR_RACELAB_USERNAME/intheloop_hybrid"
RACELAB_LOGS_DIR="/home/YOUR_RACELAB_USERNAME/jobs_logs"

# Per-module system routing for hybrid mode.
# "ucsb"    = run locally on UCSB cluster (SSH-distributed or local)
# "nersc"   = dispatch to NERSC via SSH + SLURM
# "racelab" = dispatch to racelab-gpu1 via SSH, direct run (no queue)
# If a remote machine is not reachable and a module is assigned to it, the job fails.
HYBRID_MODULE_DATA="ucsb"
HYBRID_MODULE_SIMULATIONS="ucsb"
HYBRID_MODULE_PCR="ucsb"
HYBRID_MODULE_PINN="racelab"
HYBRID_MODULE_FNO="racelab"

# Debug mode: use NERSC debug queue + minimal training params (2 epochs, tiny data)
# Set to "true" for quick end-to-end testing, "false" for production
NERSC_DEBUG=false
