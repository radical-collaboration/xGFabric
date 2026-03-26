#!/usr/bin/env python3
"""
train_fno.py  –  FNO2D training script (batch / SLURM-ready version of explore_fno.ipynb)

Usage:
    # Single-file format (one CSV per windspeed):
    python train_fno.py --data-dir /path/to/simulations

    # Multi-iteration format (subdirectories with iteration files):
    python train_fno.py --data-dir /path/to/simulations --iter-min 1500 --iter-max 2000

Output is written to:
    <output_dir>/
        model.weights.h5
        model_meta.json
        training_history.csv
        plots/
            training_curves.png
            scatter_test.png
            field_comparison.png
"""

import argparse
import gc
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

_script_start = time.time()

import matplotlib
matplotlib.use('Agg')   # non-interactive backend for cluster use
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import griddata as scipy_griddata, LinearNDInterpolator
from sklearn.model_selection import train_test_split
from tqdm import tqdm

# ── Parse args ────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Train FNO2D on CFD snapshots')
parser.add_argument('--data-dir', type=str, default=None,
                    help='Directory containing CFD simulation CSVs (single-file or multi-iteration format)')
parser.add_argument('--output-dir', type=str, default=None,
                    help='Output directory for model and results')
parser.add_argument('--iter-min', type=int, default=None,
                    help='Minimum iteration number (for multi-iteration format)')
parser.add_argument('--iter-max', type=int, default=None,
                    help='Maximum iteration number (for multi-iteration format)')
parser.add_argument('--epochs',   type=int, default=100)
parser.add_argument('--batch',    type=int, default=16)
parser.add_argument('--lr',       type=float, default=2e-3)
parser.add_argument('--patience', type=int, default=60)
args = parser.parse_args()

# Determine data format mode
USE_ITERATION_MODE = args.iter_min is not None and args.iter_max is not None
ITER_MIN = args.iter_min or 0
ITER_MAX = args.iter_max or 999999

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT       = Path(__file__).resolve().parent.parent.parent  # intheloop/
TRAINING_DIR    = REPO_ROOT / 'training'

# Simulation data directory
if args.data_dir:
    SIMULATIONS_DIR = Path(args.data_dir)
else:
    # Fallback to default
    SIMULATIONS_DIR = Path('/global/homes/k/kurl/scratch/simulations_data')

# Output directory
if args.output_dir:
    OUTPUT_DIR = Path(args.output_dir)
elif USE_ITERATION_MODE:
    OUTPUT_DIR = REPO_ROOT / 'models' / f'fno2d_iter{ITER_MIN}_{ITER_MAX}'
else:
    OUTPUT_DIR = REPO_ROOT / 'models' / 'fno2d_latest'

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR = OUTPUT_DIR / 'plots'
PLOTS_DIR.mkdir(exist_ok=True)

# Add training directory to path for shared cfd_common utilities
sys.path.insert(0, str(TRAINING_DIR))

# TF setup (must happen before import)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import tensorflow as tf  # noqa: E402
from tensorflow.keras import layers  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUTPUT_DIR / 'train.log'),
    ]
)
log = logging.getLogger(__name__)
logging.getLogger('tensorflow').setLevel(logging.ERROR)

from cfd_common import (  # noqa: E402
    filter_spatial_bounds,
    x_min, x_max, y_min, y_max,
)

mode_str = f'iterations [{ITER_MIN}, {ITER_MAX}]' if USE_ITERATION_MODE else 'single-file'
log.info('=' * 70)
log.info(f'FNO2D training  |  {mode_str}')
log.info(f'Data dir   : {SIMULATIONS_DIR}')
log.info(f'Output dir : {OUTPUT_DIR}')
log.info(f'TensorFlow : {tf.__version__}')
log.info(f'GPUs       : {tf.config.list_physical_devices("GPU")}')
log.info('=' * 70)

# =============================================================================
# 1 – Configuration
# =============================================================================
NX, NY   = 48, 24
MODES1   = 12
MODES2   = 6
HIDDEN   = 64
N_LAYERS = 4
EMBED_L  = 2
IN_CH    = 2 + 4 * EMBED_L * 2   # = 18 when EMBED_L=2

UMAG_MIN_THRESHOLD = 0.10
Z_MIN, Z_MAX       = 0.5, 5.0
Z_SLICES           = np.linspace(Z_MIN, Z_MAX, 10)
DZ_HALF            = 0.3

EPOCHS   = args.epochs
BATCH    = args.batch
LR       = args.lr
PATIENCE = args.patience
CLIP     = 1.0

log.info(f'Grid: {NX}×{NY}  modes=({MODES1},{MODES2})  hidden={HIDDEN}  layers={N_LAYERS}')
log.info(f'Training: epochs={EPOCHS}  batch={BATCH}  lr={LR}  patience={PATIENCE}')

# =============================================================================
# 2 – Discover and load data
# =============================================================================
# Regex patterns for different file naming conventions
_WS_SINGLE_RE = re.compile(r'cups_structure_ws(\d+)_')  # single-file: cups_structure_ws10_*.csv
_WS_FOLDER_RE = re.compile(r'cups_structure_ws(\d+)_')  # folder mode: cups_structure_ws10_*/
_WS_NEW_RE    = re.compile(r'sim_\d+_ws_(-?[\d.]+)_wd_')  # new format: sim_0_ws_2.00_wd_0.csv
_ITER_RE      = re.compile(r'_(\d+)\.csv$')             # iteration files: *_1500.csv

file_pairs: list[tuple[float, Path]] = []

# Check if data dir contains CSV files directly (single-file format)
# or subdirectories (multi-iteration format)
csv_files_in_dir = list(SIMULATIONS_DIR.glob('cups_structure_ws*.csv'))
csv_files_new    = list(SIMULATIONS_DIR.glob('sim_*_ws_*.csv'))
subdirs_in_dir   = [d for d in SIMULATIONS_DIR.iterdir() if d.is_dir() and _WS_FOLDER_RE.match(d.name)]

if csv_files_in_dir:
    # SINGLE-FILE FORMAT: CSVs directly in data_dir (old naming)
    log.info('Detected single-file format (one CSV per windspeed)')
    
    for csv_path in sorted(csv_files_in_dir):
        m = _WS_SINGLE_RE.match(csv_path.name)
        if m:
            ws = float(m.group(1))
            file_pairs.append((ws, csv_path))
    
    log.info(f'Found {len(file_pairs)} CSV files')

elif csv_files_new:
    # NEW FORMAT: sim_N_ws_X.XX_wd_Y.csv
    log.info('Detected new naming format (sim_N_ws_X.XX_wd_Y.csv)')
    
    for csv_path in sorted(csv_files_new):
        m = _WS_NEW_RE.search(csv_path.name)
        if m:
            ws = float(m.group(1))
            file_pairs.append((ws, csv_path))
    
    log.info(f'Found {len(file_pairs)} CSV files')
    
elif subdirs_in_dir:
    # MULTI-ITERATION FORMAT: Subdirectories per windspeed
    log.info('Detected multi-iteration format (subdirectories per windspeed)')
    
    # Newest folder per wind speed
    ws_folders: dict[int, Path] = {}
    for folder in sorted(subdirs_in_dir):
        m = _WS_FOLDER_RE.match(folder.name)
        if not m:
            continue
        ws_int = int(m.group(1))
        if ws_int not in ws_folders or folder.name > ws_folders[ws_int].name:
            ws_folders[ws_int] = folder
    
    ws_ints_sorted = sorted(ws_folders)
    log.info(f'Wind-speed folders: {ws_ints_sorted}')
    
    # Collect files in iteration range
    for ws_int, folder in sorted(ws_folders.items()):
        ws = float(ws_int)
        for csv_path in sorted(folder.iterdir()):
            im = _ITER_RE.search(csv_path.name)
            if not im:
                continue
            iteration = int(im.group(1))
            if ITER_MIN <= iteration <= ITER_MAX:
                file_pairs.append((ws, csv_path))
    
    log.info(f'CSV files in [{ITER_MIN}, {ITER_MAX}]: {len(file_pairs)}')
    
else:
    log.error(f'No CFD data found in {SIMULATIONS_DIR}')
    log.error('Expected one of:')
    log.error('  - Single-file format: cups_structure_ws<N>_*.csv files')
    log.error('  - New format: sim_<N>_ws_<X.XX>_wd_<Y>.csv files')
    log.error('  - Multi-iteration format: cups_structure_ws<N>_*/ directories')
    sys.exit(1)

if not file_pairs:
    log.error('No valid simulation files found')
    sys.exit(1)

ws_counts = pd.Series([ws for ws, _ in file_pairs]).value_counts().sort_index()
for ws_v, cnt in ws_counts.items():
    log.info(f'  ws={ws_v:.0f} m/s → {cnt} file(s)')

# Load CSVs
data_list: list[tuple[float, pd.DataFrame]] = []
for ws, csv_path in tqdm(file_pairs, desc='Loading CSVs'):
    df   = pd.read_csv(csv_path, usecols=['x', 'y', 'z', 'U_0', 'U_1', 'U_Magnitude'])
    df_f = filter_spatial_bounds(df)
    del df; gc.collect()
    df_f = df_f[df_f['U_Magnitude'] > UMAG_MIN_THRESHOLD].copy()
    if len(df_f) < 10:
        continue
    data_list.append((ws, df_f))
    gc.collect()

all_u = np.concatenate([df['U_0'].values for _, df in data_list])
all_v = np.concatenate([df['U_1'].values for _, df in data_list])
VEL_MAX   = float(max(np.abs(all_u).max(), np.abs(all_v).max()))
WS_MAX    = float(max(ws for ws, _ in data_list))
WS_values = sorted(set(ws for ws, _ in data_list))

log.info(f'Loaded {len(data_list)} (ws, snapshot) pairs')
log.info(f'WS range : {min(WS_values):.1f} – {max(WS_values):.1f} m/s ({len(WS_values)} unique)')
log.info(f'VEL_MAX  : {VEL_MAX:.4f} m/s    WS_MAX : {WS_MAX:.2f} m/s')

# =============================================================================
# 3 – Build 2D grid dataset
# =============================================================================
def sinusoidal_embed(param_val, x_grid, y_grid, L):
    channels = []
    for k in range(1, L + 1):
        channels.append((param_val * np.sin(k * 2 * np.pi * x_grid)).astype(np.float32))
        channels.append((param_val * np.cos(k * 2 * np.pi * x_grid)).astype(np.float32))
        channels.append((param_val * np.sin(k * 2 * np.pi * y_grid)).astype(np.float32))
        channels.append((param_val * np.cos(k * 2 * np.pi * y_grid)).astype(np.float32))
    return np.stack(channels, axis=-1)

x_lin = np.linspace(x_min, x_max, NX)
y_lin = np.linspace(y_min, y_max, NY)
xx, yy = np.meshgrid(x_lin, y_lin, indexing='ij')

x_norm_grid = ((xx - x_min) / (x_max - x_min + 1e-12)).astype(np.float32)
y_norm_grid = ((yy - y_min) / (y_max - y_min + 1e-12)).astype(np.float32)

samples_X, samples_Y, sample_meta = [], [], []

# Cache Delaunay triangulations per z-slice (same CFD mesh across all files).
# scipy_griddata rebuilds the triangulation on every call; LinearNDInterpolator
# lets us build it once and reuse it by swapping values — ~N_files× speedup.
_z_interp_u: dict[float, LinearNDInterpolator] = {}
_z_interp_v: dict[float, LinearNDInterpolator] = {}
_z_pts_hash: dict[float, int] = {}   # hash of pts shape to detect mesh changes

query_pts = np.column_stack([xx.ravel(), yy.ravel()])

for ws, df in tqdm(data_list, desc='Building grids'):
    ws_n = float(ws / (WS_MAX + 1e-8))
    for z_s in Z_SLICES:
        z_n = float((z_s - Z_MIN) / (Z_MAX - Z_MIN + 1e-12))
        mask = np.abs(df['z'].values - z_s) <= DZ_HALF
        df_z = df[mask]
        if len(df_z) < 10:
            continue
        pts  = df_z[['x', 'y']].values
        u_n  = df_z['U_0'].values / (VEL_MAX + 1e-8)
        v_n  = df_z['U_1'].values / (VEL_MAX + 1e-8)

        pts_key = (z_s, pts.shape[0])
        if z_s not in _z_interp_u or _z_pts_hash.get(z_s) != pts_key:
            # First time or mesh changed — build triangulation from scratch
            _z_interp_u[z_s] = LinearNDInterpolator(pts, u_n, fill_value=0.0)
            _z_interp_v[z_s] = LinearNDInterpolator(pts, v_n, fill_value=0.0)
            _z_pts_hash[z_s] = pts_key
        else:
            # Reuse existing triangulation, swap values only
            _z_interp_u[z_s].values = u_n.reshape(-1, 1).astype(np.float64)
            _z_interp_v[z_s].values = v_n.reshape(-1, 1).astype(np.float64)

        u_grid = _z_interp_u[z_s](query_pts).reshape(NX, NY).astype(np.float32)
        v_grid = _z_interp_v[z_s](query_pts).reshape(NX, NY).astype(np.float32)
        ws_embed = sinusoidal_embed(ws_n, x_norm_grid, y_norm_grid, EMBED_L)
        z_embed  = sinusoidal_embed(z_n,  x_norm_grid, y_norm_grid, EMBED_L)
        inp = np.concatenate([
            x_norm_grid[..., np.newaxis],
            y_norm_grid[..., np.newaxis],
            ws_embed,
            z_embed,
        ], axis=-1)
        out = np.stack([u_grid, v_grid], axis=-1)
        samples_X.append(inp)
        samples_Y.append(out)
        sample_meta.append({'ws': ws, 'z': z_s})

X_fno = np.stack(samples_X, axis=0)
Y_fno = np.stack(samples_Y, axis=0)
assert X_fno.shape[-1] == IN_CH, f'IN_CH mismatch: expected {IN_CH}, got {X_fno.shape[-1]}'

idx_all        = np.arange(len(X_fno))
tr_idx, te_idx = train_test_split(idx_all, test_size=0.15, random_state=42)
tr_idx, vl_idx = train_test_split(tr_idx,  test_size=0.15, random_state=42)

X_tr, Y_tr = X_fno[tr_idx], Y_fno[tr_idx]
X_vl, Y_vl = X_fno[vl_idx], Y_fno[vl_idx]
X_te, Y_te = X_fno[te_idx], Y_fno[te_idx]

log.info(f'Dataset  X={X_fno.shape}  Y={Y_fno.shape}')
log.info(f'Split    train={len(X_tr)} / val={len(X_vl)} / test={len(X_te)}')

# =============================================================================
# 4 – Model definition
# =============================================================================
class SpectralConv2d(layers.Layer):
    def __init__(self, in_ch, out_ch, modes1, modes2, **kwargs):
        super().__init__(**kwargs)
        self.modes1, self.modes2 = modes1, modes2
        scale = 1.0 / (in_ch * out_ch)
        self.wr = self.add_weight(name='wr', shape=(modes1, modes2, in_ch, out_ch),
                                  initializer=tf.keras.initializers.TruncatedNormal(stddev=scale))
        self.wi = self.add_weight(name='wi', shape=(modes1, modes2, in_ch, out_ch),
                                  initializer=tf.keras.initializers.TruncatedNormal(stddev=scale))

    def _compl_mul(self, x_r, x_i):
        out_r = tf.einsum('bmni,mnio->bmno', x_r, self.wr) - tf.einsum('bmni,mnio->bmno', x_i, self.wi)
        out_i = tf.einsum('bmni,mnio->bmno', x_r, self.wi) + tf.einsum('bmni,mnio->bmno', x_i, self.wr)
        return out_r, out_i

    def call(self, x):
        NX_ = tf.shape(x)[1]; NY_ = tf.shape(x)[2]
        xp   = tf.transpose(x, [0, 3, 1, 2])
        x_ft = tf.signal.rfft2d(xp)
        x_ft = tf.transpose(x_ft, [0, 2, 3, 1])
        x_low = x_ft[:, :self.modes1, :self.modes2, :]
        out_r, out_i = self._compl_mul(tf.math.real(x_low), tf.math.imag(x_low))
        ny_half  = NY_ // 2 + 1
        paddings = [[0, 0], [0, NX_ - self.modes1], [0, ny_half - self.modes2], [0, 0]]
        out_ft   = tf.complex(tf.pad(out_r, paddings), tf.pad(out_i, paddings))
        out_sp   = tf.signal.irfft2d(tf.transpose(out_ft, [0, 3, 1, 2]))
        return tf.transpose(out_sp, [0, 2, 3, 1])


class FNOBlock(layers.Layer):
    def __init__(self, hidden, modes1, modes2, **kwargs):
        super().__init__(**kwargs)
        self.spec  = SpectralConv2d(hidden, hidden, modes1, modes2)
        self.local = layers.Dense(hidden, use_bias=True)
        self.norm  = layers.LayerNormalization()

    def call(self, x, training=False):
        return tf.nn.gelu(self.norm(self.spec(x) + self.local(x), training=training))


class FNO2D(tf.keras.Model):
    def __init__(self, in_ch, out_ch, hidden, n_layers, modes1, modes2, **kwargs):
        super().__init__(**kwargs)
        self.lift   = layers.Dense(hidden)
        self.blocks = [FNOBlock(hidden, modes1, modes2, name=f'fno_block_{i}') for i in range(n_layers)]
        self.proj1  = layers.Dense(hidden // 2, activation='gelu')
        self.proj2  = layers.Dense(out_ch)

    def call(self, x, training=False):
        v = self.lift(x)
        for block in self.blocks:
            v = block(v, training=training)
        return self.proj2(self.proj1(v))


fno = FNO2D(in_ch=IN_CH, out_ch=2, hidden=HIDDEN, n_layers=N_LAYERS,
            modes1=MODES1, modes2=MODES2, name='fno2d')
_ = fno(tf.constant(X_tr[:2]))
n_params = sum(np.prod(v.shape) for v in fno.trainable_variables)
log.info(f'FNO2D  {n_params:,} trainable parameters')

# =============================================================================
# 5 – Training
# =============================================================================
n_batches = max(len(X_tr) // BATCH, 1)
lr_sched  = tf.keras.optimizers.schedules.CosineDecay(LR, decay_steps=EPOCHS * n_batches)
opt       = tf.keras.optimizers.Adam(learning_rate=lr_sched)
loss_fn   = tf.keras.losses.MeanSquaredError()

ds_tr = (tf.data.Dataset.from_tensor_slices((X_tr, Y_tr))
           .shuffle(len(X_tr), seed=42).batch(BATCH).prefetch(tf.data.AUTOTUNE))
ds_vl = tf.data.Dataset.from_tensor_slices((X_vl, Y_vl)).batch(BATCH)

hist  = {'epoch': [], 'train_loss': [], 'val_loss': []}
best_val = float('inf')
best_w   = None
pat      = 0
ep       = 0
t0       = time.time()

log.info(f'Starting training  ({len(X_tr)} train / {len(X_vl)} val samples)')

for ep in range(EPOCHS):
    tr_losses = []
    for xb, yb in ds_tr:
        with tf.GradientTape() as tape:
            tr_loss = loss_fn(yb, fno(xb, training=True))
        grads, _ = tf.clip_by_global_norm(tape.gradient(tr_loss, fno.trainable_variables), CLIP)
        opt.apply_gradients(zip(grads, fno.trainable_variables))
        tr_losses.append(float(tr_loss))

    avg_tr = float(np.mean(tr_losses))
    avg_vl = float(np.mean([float(loss_fn(yb, fno(xb, training=False))) for xb, yb in ds_vl]))

    if ep % 10 == 0 or ep == EPOCHS - 1:
        hist['epoch'].append(ep)
        hist['train_loss'].append(avg_tr)
        hist['val_loss'].append(avg_vl)
        log.info(f'epoch {ep:4d}  train={avg_tr:.4e}  val={avg_vl:.4e}  best={best_val:.4e}  pat={pat}/{PATIENCE}')

    if avg_vl < best_val:
        best_val = avg_vl
        best_w   = fno.get_weights()
        pat      = 0
    else:
        pat += 1

    if pat >= PATIENCE:
        log.info(f'Early stop at epoch {ep}')
        break

if best_w is not None:
    fno.set_weights(best_w)

elapsed = time.time() - t0
log.info(f'Training done  best_val_mse={best_val:.6e}  ({elapsed/60:.1f} min)')

# =============================================================================
# 6 – Save model
# =============================================================================
fno.save_weights(str(OUTPUT_DIR / 'model.weights.h5'))

meta = {
    'model_class'    : 'FNO2D',
    'hidden'         : HIDDEN,
    'n_layers'       : N_LAYERS,
    'modes1'         : MODES1,
    'modes2'         : MODES2,
    'NX'             : NX,
    'NY'             : NY,
    'in_ch'          : int(X_tr.shape[-1]),
    'embed_L'        : EMBED_L,
    'input_encoding' : 'x_norm, y_norm, sinusoidal_ws(EMBED_L), sinusoidal_z(EMBED_L)',
    'best_val_mse'   : float(best_val),
    'epochs_trained' : int(ep + 1),
    'VEL_MAX'        : VEL_MAX,
    'WS_MAX'         : WS_MAX,
    'ITER_MIN'       : ITER_MIN,
    'ITER_MAX'       : ITER_MAX,
    'Z_MIN'          : Z_MIN,
    'Z_MAX'          : Z_MAX,
    'x_min'          : float(x_min),
    'x_max'          : float(x_max),
    'y_min'          : float(y_min),
    'y_max'          : float(y_max),
    'output_channels': ['u_norm', 'v_norm'],
}

with open(OUTPUT_DIR / 'model_meta.json', 'w') as f:
    json.dump(meta, f, indent=2)

pd.DataFrame(hist).to_csv(OUTPUT_DIR / 'training_history.csv', index=False)
log.info(f'Model saved to {OUTPUT_DIR}')

# =============================================================================
# 7 – Evaluate & save plots
# =============================================================================
pred_te  = fno(tf.constant(X_te, dtype=tf.float32), training=False).numpy()
true_te  = Y_te

pred_u_ms = pred_te[..., 0] * VEL_MAX;  true_u_ms = true_te[..., 0] * VEL_MAX
pred_v_ms = pred_te[..., 1] * VEL_MAX;  true_v_ms = true_te[..., 1] * VEL_MAX
pred_spd  = np.sqrt(pred_u_ms**2 + pred_v_ms**2)
true_spd  = np.sqrt(true_u_ms**2 + true_v_ms**2)

rmse_u   = float(np.sqrt(np.mean((pred_u_ms - true_u_ms)**2)))
rmse_v   = float(np.sqrt(np.mean((pred_v_ms - true_v_ms)**2)))
rmse_spd = float(np.sqrt(np.mean((pred_spd  - true_spd )**2)))
mae_spd  = float(np.mean(np.abs(pred_spd - true_spd)))

log.info('─' * 50)
log.info(f'  RMSE(u)     : {rmse_u:.4f} m/s')
log.info(f'  RMSE(v)     : {rmse_v:.4f} m/s')
log.info(f'  RMSE(speed) : {rmse_spd:.4f} m/s')
log.info(f'  MAE(speed)  : {mae_spd:.4f} m/s')
log.info('─' * 50)

# Save metrics JSON
with open(OUTPUT_DIR / 'test_metrics.json', 'w') as f:
    json.dump({'rmse_u': rmse_u, 'rmse_v': rmse_v,
               'rmse_speed': rmse_spd, 'mae_speed': mae_spd}, f, indent=2)

# Plot 1: training curves
fig, ax = plt.subplots(figsize=(8, 5))
ax.semilogy(hist['epoch'], hist['train_loss'], 'C0', label='train')
ax.semilogy(hist['epoch'], hist['val_loss'],   'C1', label='val')
ax.set_xlabel('Epoch'); ax.set_ylabel('MSE loss')
ax.set_title(f'FNO2D training curves  |  iters [{ITER_MIN}, {ITER_MAX}]')
ax.legend(); ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(PLOTS_DIR / 'training_curves.png', dpi=150)
plt.close(fig)

# Plot 2: scatter pred vs true speed
fig, ax = plt.subplots(figsize=(6, 6))
ax.scatter(true_spd.ravel(), pred_spd.ravel(), s=1, alpha=0.15)
lm = [true_spd.min(), true_spd.max()]
ax.plot(lm, lm, 'r--', lw=1.5, label='ideal')
ax.set_xlabel('True speed (m/s)'); ax.set_ylabel('Predicted speed (m/s)')
ax.set_title(f'FNO2D scatter (test)  RMSE={rmse_spd:.3f} m/s\niters [{ITER_MIN}, {ITER_MAX}]')
ax.set_aspect('equal'); ax.legend(); ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(PLOTS_DIR / 'scatter_test.png', dpi=150)
plt.close(fig)

# Plot 3: field comparison for first test sample
sample_idx = 0
meta_s  = sample_meta[te_idx[sample_idx]]
err     = np.abs(pred_spd[sample_idx] - true_spd[sample_idx])
spd_vmin = min(true_spd[sample_idx].min(), pred_spd[sample_idx].min())
spd_vmax = max(true_spd[sample_idx].max(), pred_spd[sample_idx].max())

fig, axes = plt.subplots(1, 3, figsize=(21, 5))
kw   = dict(origin='lower', aspect='auto', extent=[x_min, x_max, y_min, y_max],
            cmap='RdBu_r', vmin=spd_vmin, vmax=spd_vmax)
kw_e = dict(origin='lower', aspect='auto', extent=[x_min, x_max, y_min, y_max],
            cmap='Reds', vmin=0, vmax=err.max())
for ax, data, title, ckw in zip(
        axes,
        [true_spd[sample_idx].T, pred_spd[sample_idx].T, err.T],
        ['CFD truth', 'FNO prediction', 'Absolute error'],
        [kw, kw, kw_e]):
    im = ax.imshow(data, **ckw)
    plt.colorbar(im, ax=ax, label='m/s')
    ax.set_xlabel('x (m)'); ax.set_ylabel('y (m)')
    ax.set_title(f'{title}  ws={meta_s["ws"]:.1f} m/s, z={meta_s["z"]:.1f} m')
fig.suptitle(f'FNO2D field comparison  |  iters [{ITER_MIN}, {ITER_MAX}]', fontsize=13)
fig.tight_layout()
fig.savefig(PLOTS_DIR / 'field_comparison.png', dpi=150)
plt.close(fig)

log.info(f'Plots saved to {PLOTS_DIR}')
_total = time.time() - _script_start
_h, _m, _s = int(_total//3600), int((_total%3600)//60), int(_total%60)
log.info(f'[TIMER] total={_h}h {_m}m {_s}s  ({_total/60:.1f} min)')
log.info('✓ All done')
