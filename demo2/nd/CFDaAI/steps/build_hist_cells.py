#!/usr/bin/env python3
"""Build and insert historical evaluation cells into step_analysis.ipynb."""
import json, uuid
from pathlib import Path

NB_PATH = Path("/local/home/liubov_kurafeeva/intheloop/steps/step_analysis.ipynb")

with open(NB_PATH) as f:
    nb = json.load(f)

# Keep only cells 0-5
nb["cells"] = nb["cells"][:6]

def cell_id():
    return uuid.uuid4().hex[:8]

def md(src):
    return {"cell_type": "markdown", "id": cell_id(), "metadata": {},
            "source": src}

def code(src):
    return {"cell_type": "code", "id": cell_id(), "metadata": {},
            "execution_count": None, "outputs": [], "source": src}

# ── Section 3: Historical Eval Config ────────────────────────────────────────
SEC3_MD = """\
---
## 3  Historical Evaluation: Model Versions vs Real Sensor Data

Evaluate models from steps 10–20 against real indoor sensor data.

For each sampled timestamp **t** in the evaluation window:
- Identify the **N_POOL most-recent** model groups whose training cutoff ≤ t
- Run PCR / PINN / FNO inference using outdoor wind speed at t as input
- Compare predicted indoor speed to the corresponding sensor reading
- Plot MAE per model version for each model type separately
"""

SEC3_CODE = """\
# ── Historical Evaluation Config ──────────────────────────────────────────────
HIST_DATA_DIR  = Path("/local/home/liubov_kurafeeva/storage/cups_historical")
CACHE_FILE     = Path("/local/home/liubov_kurafeeva/intheloop/steps/hist_eval_cache.pkl")

STEPS_EVAL     = list(range(10, 21))   # steps 10-20 inclusive
N_POOL         = 3                      # most-recent eligible model groups per timestamp
N_TIME_GROUPS  = 24                    # evenly-spaced timestamps in evaluation window

# Sensor positions in CFD domain (metres)
SENSORS = {
    "davis_in": {"x": 41.0,  "y": 48.0, "z": 5.0},
    "wu31":     {"x": 104.0, "y": 48.0, "z": 1.0},
    "wu30":     {"x": 166.0, "y": 48.0, "z": 1.0},
}

# Indoor CSV config: (filename, windspeed_col, data_field_index)
# data_field_index: colon-split index for raw CSPOT format (None if explicit col)
INDOOR_CFG = {
    "davis_in": ("davis_cupsin_north.csv",  None,         4),
    "wu31":     ("cups_inside_middle.csv",  "windspeed",  None),
    "wu30":     ("cups_inside_south.csv",   "windspeed",  None),
}

# Outdoor sensor file (raw CSPOT format, field[3]=windspeed mph)
OUTDOOR_FILE = "davis_cupsout_north.csv"

MPH_TO_MS = 0.44704
FORCE_RECOMPUTE = False   # set True to ignore cache

print("Config loaded. Steps to evaluate:", STEPS_EVAL)
"""

# ── Section 4: Load Sensor Data ───────────────────────────────────────────────
SEC4_MD = """\
---
## 4  Load Historical Sensor Data & Sample Evaluation Timestamps
"""

SEC4_CODE = """\
import csv
from datetime import datetime, timezone, timedelta
import random

random.seed(42)


def parse_dt_utc(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def load_outdoor_series(hist_dir):
    \"\"\"Return list of (datetime, windspeed_ms) from davis_cupsout_north.csv.\"\"\"
    fpath = Path(hist_dir) / OUTDOOR_FILE
    series = []
    with open(fpath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = parse_dt_utc(row.get("dt", ""))
            if dt is None:
                continue
            data_str = row.get("data", "")
            try:
                fields = data_str.split(":")
                ws_mph = float(fields[3])
                series.append((dt, ws_mph * MPH_TO_MS))
            except (ValueError, IndexError):
                continue
    series.sort(key=lambda x: x[0])
    print(f"Outdoor series: {len(series)} records, "
          f"{series[0][0].date()} → {series[-1][0].date()}")
    return series


def load_indoor_series(hist_dir, sensor_name):
    \"\"\"Return list of (datetime, windspeed_ms) for a given indoor sensor.\"\"\"
    fname, ws_col, data_idx = INDOOR_CFG[sensor_name]
    fpath = Path(hist_dir) / fname
    series = []
    with open(fpath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = parse_dt_utc(row.get("dt", ""))
            if dt is None:
                continue
            try:
                if ws_col is not None:
                    ws_mph = float(row[ws_col])
                else:
                    fields = row.get("data", "").split(":")
                    ws_mph = float(fields[data_idx])
                series.append((dt, ws_mph * MPH_TO_MS))
            except (ValueError, IndexError, KeyError):
                continue
    series.sort(key=lambda x: x[0])
    print(f"  {sensor_name}: {len(series)} records")
    return series


# Load data
outdoor_series = load_outdoor_series(HIST_DATA_DIR)

indoor_series = {}
print("Loading indoor sensor data:")
for sname in SENSORS:
    indoor_series[sname] = load_indoor_series(HIST_DATA_DIR, sname)

# Determine evaluation window from steps 10-20
eval_steps_df = df[df["step_num"].isin(STEPS_EVAL)].dropna(subset=["cutoff_date"])
cutoff_times  = sorted(eval_steps_df["cutoff_date"].tolist())
t_start       = cutoff_times[0]                   # first cutoff date (step 10)
t_end         = cutoff_times[-1] + timedelta(hours=24)

print(f"\\nEvaluation window: {t_start} → {t_end}")

# Filter outdoor series to window
outdoor_window = [(dt, ws) for dt, ws in outdoor_series if t_start <= dt <= t_end]
print(f"Outdoor records in window: {len(outdoor_window)}")

# Sample N_TIME_GROUPS evenly-spaced timestamps
if len(outdoor_window) >= N_TIME_GROUPS:
    step_size = len(outdoor_window) // N_TIME_GROUPS
    eval_records = [outdoor_window[i * step_size] for i in range(N_TIME_GROUPS)]
else:
    eval_records = outdoor_window

eval_timestamps = [dt for dt, _ in eval_records]
print(f"Sampled {len(eval_timestamps)} evaluation timestamps")


def nearest_indoor(sensor_name, target_dt, max_delta_min=15):
    \"\"\"Return windspeed_ms from indoor sensor closest to target_dt, or None.\"\"\"
    best_dt, best_ws = None, None
    best_delta = timedelta(minutes=max_delta_min + 1)
    for dt, ws in indoor_series[sensor_name]:
        delta = abs(dt - target_dt)
        if delta < best_delta:
            best_delta = delta
            best_dt, best_ws = dt, ws
    return best_ws if best_delta <= timedelta(minutes=max_delta_min) else None


def outdoor_history_before(target_dt, n=72):
    \"\"\"Return list of (datetime, windspeed_ms) for the n records before target_dt.\"\"\"
    before = [(dt, ws) for dt, ws in outdoor_series if dt <= target_dt]
    return before[-n:]
"""

# ── Section 5: Preload Models ─────────────────────────────────────────────────
SEC5_MD = """\
---
## 5  Preload Models for Steps 10–20
"""

SEC5_CODE = """\
import sys
import numpy as np
import importlib.util
import tensorflow as tf

# ── PCR loader ────────────────────────────────────────────────────────────────
def load_pcr_coefs(pcr_root, x, y, z):
    \"\"\"Load PCR coefficients for the nearest grid point to (x, y, z).\"\"\"
    best_f, best_d = None, float("inf")
    for f in sorted(Path(pcr_root).glob("pcr_coefficients_*.csv")):
        parts = f.stem.split("_")
        try:
            cx, cy, cz = float(parts[-3].rstrip("p").replace("p",".")), \\
                         float(parts[-2].rstrip("p").replace("p",".")), \\
                         float(parts[-1].rstrip("p").replace("p","."))
        except (ValueError, IndexError):
            try:
                coords = [p for p in parts if p.replace(".","").isdigit()]
                cx, cy, cz = float(coords[-3]), float(coords[-2]), float(coords[-1])
            except Exception:
                continue
        d = (cx-x)**2 + (cy-y)**2 + (cz-z)**2
        if d < best_d:
            best_d, best_f = d, f
    if best_f is None:
        return None
    rows = []
    with open(best_f) as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    if not rows:
        return None
    def _arr(key):
        return np.array([float(r[key]) for r in rows])
    r0 = rows[0]
    coefs = {
        "scaler_mean":      float(r0.get("scaler_mean", 0)),
        "scaler_scale":     float(r0.get("scaler_scale", 1)),
        "pca_mean":         _arr("pca_mean"),
        "pca_components":   _arr("pca_component").reshape(1,-1),
        "reg_coef":         _arr("reg_coef").reshape(1,-1),
        "reg_intercept":    float(r0.get("reg_intercept", 0)),
        "sequence_length":  int(r0.get("sequence_length", 72)),
    }
    return coefs


def pcr_predict_one(coefs, ws_history_ms):
    seq = np.asarray([ws for _, ws in ws_history_ms[-coefs["sequence_length"]:]], dtype=float)
    if len(seq) < coefs["sequence_length"]:
        return np.nan
    scaled    = (seq - coefs["scaler_mean"]) / (coefs["scaler_scale"] + 1e-12)
    centered  = scaled - coefs["pca_mean"]
    projected = coefs["pca_components"] @ centered
    return float(coefs["reg_coef"] @ projected + coefs["reg_intercept"])


# ── PINN loader ───────────────────────────────────────────────────────────────
def load_pinn_model(pinn_dir):
    \"\"\"Load PINN weights and normalization from archive directory.\"\"\"
    pinn_dir = Path(pinn_dir)
    # Find meta and norm files
    meta_f = next(pinn_dir.glob("*meta*.json"), None)
    norm_f = next(pinn_dir.glob("*norm*.json"), None)
    wts_f  = next(pinn_dir.glob("*.weights.h5"), None)
    if meta_f is None or norm_f is None or wts_f is None:
        return None
    with open(meta_f) as f: meta = json.load(f)
    with open(norm_f) as f: norm = json.load(f)

    # Build PhysicsMLP3D
    hidden_units = meta.get("hidden_units", [128, 128, 128])
    inp_dim      = meta.get("input_dim", 4)
    out_dim      = meta.get("output_dim", 2)

    inp = tf.keras.Input(shape=(inp_dim,))
    x   = inp
    for u in hidden_units:
        x = tf.keras.layers.Dense(u, activation="tanh")(x)
    out = tf.keras.layers.Dense(out_dim)(x)
    model = tf.keras.Model(inp, out)
    model.load_weights(str(wts_f))
    return {"model": model, "norm": norm, "meta": meta}


def pinn_predict_one(pinn_bundle, sensor_name, outdoor_ms):
    \"\"\"Predict indoor wind speed at sensor_name given scalar outdoor_ms.\"\"\"
    norm  = pinn_bundle["norm"]
    model = pinn_bundle["model"]
    sx    = SENSORS[sensor_name]
    WS_MAX   = float(norm.get("ws_max",   20.0))
    VEL_MAX  = float(norm.get("vel_max",  20.0))
    X_RANGE  = norm.get("x_range",  [0, 210])
    Y_RANGE  = norm.get("y_range",  [0, 96])
    Z_RANGE  = norm.get("z_range",  [0, 10])
    x_norm = (sx["x"] - X_RANGE[0]) / (X_RANGE[1] - X_RANGE[0] + 1e-9)
    y_norm = (sx["y"] - Y_RANGE[0]) / (Y_RANGE[1] - Y_RANGE[0] + 1e-9)
    z_norm = (sx["z"] - Z_RANGE[0]) / (Z_RANGE[1] - Z_RANGE[0] + 1e-9)
    ws_norm = outdoor_ms / (WS_MAX + 1e-9)
    inp = np.array([[x_norm, y_norm, z_norm, ws_norm]], dtype=np.float32)
    uv  = model(inp, training=False).numpy()[0]
    speed = float(np.sqrt(uv[0]**2 + uv[1]**2)) * VEL_MAX
    return speed


# ── FNO loader ────────────────────────────────────────────────────────────────
FNO_MOD_PATH = "/local/home/liubov_kurafeeva/intheloop/ben/inferencing/fno.py"

_fno_spec = importlib.util.spec_from_file_location("fno_mod", FNO_MOD_PATH)
_fno_mod  = importlib.util.module_from_spec(_fno_spec)
_fno_spec.loader.exec_module(_fno_mod)
FNO2D = _fno_mod.FNO2D


def load_fno_model(fno_dir):
    fno_dir  = Path(fno_dir)
    meta_f   = next(fno_dir.glob("model_meta.json"), None)
    wts_f    = next(fno_dir.glob("model.weights.h5"), None)
    if meta_f is None or wts_f is None:
        return None
    with open(meta_f) as f: meta = json.load(f)
    fno = FNO2D(
        in_ch   = meta["in_ch"],
        out_ch  = meta["out_ch"],
        hidden  = meta["hidden"],
        n_layers= meta["n_layers"],
        modes1  = meta["modes1"],
        modes2  = meta["modes2"],
    )
    # Build with dummy input to initialise weights
    NX = meta.get("NX", 48)
    NY = meta.get("NY", 24)
    in_ch = meta["in_ch"]
    _ = fno(tf.zeros((1, NX, NY, in_ch)), training=False)
    fno.load_weights(str(wts_f))
    return {"model": fno, "meta": meta}


def fno_predict_one(fno_bundle, sensor_name, outdoor_ms):
    \"\"\"Predict indoor speed at sensor using FNO.\"\"\"
    meta  = fno_bundle["meta"]
    model = fno_bundle["model"]
    NX    = meta.get("NX", 48)
    NY    = meta.get("NY", 24)
    in_ch = meta["in_ch"]
    NZ    = meta.get("NZ", 10)
    WS_MAX  = float(meta.get("ws_max",  20.0))
    VEL_MAX = float(meta.get("vel_max", 20.0))

    sx = SENSORS[sensor_name]
    DX = meta.get("dx", 210.0 / NX)
    DY = meta.get("dy", 96.0  / NY)
    gi = int(np.clip(sx["x"] / DX, 0, NX - 1))
    gj = int(np.clip(sx["y"] / DY, 0, NY - 1))

    # Build input grid  (1, NX, NY, in_ch)
    ws_norm  = outdoor_ms / (WS_MAX + 1e-9)
    z_norm   = sx["z"] / (NZ + 1e-9)

    # Basic sinusoidal embedding (match training convention)
    grid = np.zeros((1, NX, NY, in_ch), dtype=np.float32)
    # channels 0,1: spatial frequencies
    for i in range(NX):
        for j in range(NY):
            xi = i / NX; yj = j / NY
            base = [np.sin(np.pi * xi), np.cos(np.pi * xi),
                    np.sin(np.pi * yj), np.cos(np.pi * yj)]
            # remaining channels: ws and z broadcast
            extra = [ws_norm, z_norm] + [0.0] * max(0, in_ch - 6)
            row = (base + extra)[:in_ch]
            grid[0, i, j, :len(row)] = row

    out = model(tf.constant(grid), training=False).numpy()   # (1, NX, NY, 2)
    uv  = out[0, gi, gj, :]
    return float(np.sqrt(uv[0]**2 + uv[1]**2)) * VEL_MAX


# ── Preload all models ────────────────────────────────────────────────────────
print("Preloading models for steps 10–20 ...")
model_store = {}   # step_num -> {"cutoff": dt, "pcr": {sname: coefs}, "pinn": bundle, "fno": bundle}

for snum in STEPS_EVAL:
    row = df[df["step_num"] == snum]
    if row.empty or row.iloc[0]["status"] != "done":
        print(f"  Step {snum:02d}: skipped (not done)")
        continue
    arch = row.iloc[0]["archive_path"]
    if not arch or not Path(arch).exists():
        print(f"  Step {snum:02d}: archive missing ({arch})")
        continue

    arch_p  = Path(arch)
    iter1   = arch_p / "iteration_1"
    pcr_dir = iter1 / "models" / "pcr"
    pinn_dir= iter1 / "models" / "pinn"
    fno_dir = iter1 / "models" / "fno"

    cutoff = row.iloc[0]["cutoff_date"]

    entry = {"cutoff": cutoff, "pcr": {}, "pinn": None, "fno": None}

    # PCR per sensor
    for sname, scfg in SENSORS.items():
        if pcr_dir.exists():
            for part in sorted(pcr_dir.iterdir()):
                coefs = load_pcr_coefs(str(part), scfg["x"], scfg["y"], scfg["z"])
                if coefs:
                    entry["pcr"][sname] = coefs
                    break

    # PINN
    if pinn_dir.exists():
        entry["pinn"] = load_pinn_model(pinn_dir)

    # FNO
    if fno_dir.exists():
        entry["fno"] = load_fno_model(fno_dir)

    has = [k for k, v in entry.items() if k != "cutoff" and (v if not isinstance(v, dict) else v)]
    print(f"  Step {snum:02d}: cutoff={cutoff}  loaded: {has}")
    model_store[snum] = entry

print(f"Done. {len(model_store)} model groups preloaded.")
"""

# ── Section 6: Run Evaluation Loop ───────────────────────────────────────────
SEC6_MD = """\
---
## 6  Run Evaluation Loop (with Cache)
"""

SEC6_CODE = """\
import pickle

def run_evaluation():
    \"\"\"
    For each eval timestamp:
      - Find N_POOL most-recent eligible model groups (cutoff <= t)
      - For each model group and each sensor: predict and compute MAE
    Returns list of result dicts.
    \"\"\"
    results = []
    sorted_steps = sorted(model_store.keys())

    for ts_idx, (eval_dt, outdoor_ms) in enumerate(eval_records):
        # Eligible groups: cutoff <= eval_dt
        eligible = [s for s in sorted_steps
                    if model_store[s]["cutoff"] <= eval_dt]
        if not eligible:
            continue
        pool = eligible[-N_POOL:]  # N most recent

        for snum in pool:
            entry   = model_store[snum]
            cutoff  = entry["cutoff"]
            hist    = outdoor_history_before(eval_dt)
            true_speeds = {}
            for sname in SENSORS:
                true_speeds[sname] = nearest_indoor(sname, eval_dt)

            rec = {
                "eval_dt":     eval_dt,
                "outdoor_ms":  outdoor_ms,
                "step_num":    snum,
                "cutoff":      cutoff,
            }

            for sname in SENSORS:
                true_ws = true_speeds[sname]

                # PCR
                pcr_pred = np.nan
                coefs = entry["pcr"].get(sname)
                if coefs and hist:
                    try:
                        pcr_pred = pcr_predict_one(coefs, hist)
                    except Exception:
                        pass
                rec[f"pcr_{sname}_pred"]  = pcr_pred
                rec[f"pcr_{sname}_true"]  = true_ws
                rec[f"pcr_{sname}_mae"]   = abs(pcr_pred - true_ws) if (true_ws is not None and not np.isnan(pcr_pred)) else np.nan

                # PINN
                pinn_pred = np.nan
                if entry["pinn"]:
                    try:
                        pinn_pred = pinn_predict_one(entry["pinn"], sname, outdoor_ms)
                    except Exception:
                        pass
                rec[f"pinn_{sname}_pred"] = pinn_pred
                rec[f"pinn_{sname}_true"] = true_ws
                rec[f"pinn_{sname}_mae"]  = abs(pinn_pred - true_ws) if (true_ws is not None and not np.isnan(pinn_pred)) else np.nan

                # FNO
                fno_pred = np.nan
                if entry["fno"]:
                    try:
                        fno_pred = fno_predict_one(entry["fno"], sname, outdoor_ms)
                    except Exception:
                        pass
                rec[f"fno_{sname}_pred"]  = fno_pred
                rec[f"fno_{sname}_true"]  = true_ws
                rec[f"fno_{sname}_mae"]   = abs(fno_pred - true_ws) if (true_ws is not None and not np.isnan(fno_pred)) else np.nan

            results.append(rec)

    return results


if not FORCE_RECOMPUTE and CACHE_FILE.exists():
    print(f"Loading cached results from {CACHE_FILE}")
    with open(CACHE_FILE, "rb") as f:
        eval_results = pickle.load(f)
else:
    print("Running evaluation loop ...")
    eval_results = run_evaluation()
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(eval_results, f)
    print(f"Saved to {CACHE_FILE}")

edf = pd.DataFrame(eval_results)
print(f"Evaluation results: {len(edf)} rows, {len(edf.columns)} columns")
edf.head(3)
"""

# ── Section 7: PCR Comparison ─────────────────────────────────────────────────
SEC7_MD = """\
---
## 7  PCR Model Versions vs Real Indoor Wind Speed

Each line = a different training step (model version). X-axis = evaluation time.
Lower MAE = better. Newer models (higher step number) should improve over time.
"""

SEC7_CODE = """\
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

STEP_COLORS = plt.cm.viridis(np.linspace(0.15, 0.9, len(STEPS_EVAL)))
step_color_map = {s: STEP_COLORS[i] for i, s in enumerate(STEPS_EVAL)}

sensor_names = list(SENSORS.keys())
n_sensors    = len(sensor_names)

fig, axes = plt.subplots(n_sensors, 1, figsize=(14, 4 * n_sensors), sharex=True)
if n_sensors == 1:
    axes = [axes]

for ax, sname in zip(axes, sensor_names):
    for snum in sorted(edf["step_num"].unique()):
        sdf = edf[edf["step_num"] == snum].dropna(subset=[f"pcr_{sname}_mae"])
        if sdf.empty:
            continue
        sdf = sdf.sort_values("eval_dt")
        ax.plot(sdf["eval_dt"], sdf[f"pcr_{sname}_mae"],
                marker="o", ms=4, lw=1.5,
                color=step_color_map.get(snum, "gray"),
                label=f"Step {snum:02d} (cutoff {model_store[snum]['cutoff'].strftime('%m-%d %H:%M')})")

    ax.set_ylabel("MAE (m/s)")
    ax.set_title(f"PCR — sensor: {sname}")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))

axes[0].legend(fontsize=8, loc="upper right")
axes[-1].set_xlabel("Evaluation timestamp (UTC)")
fig.suptitle("PCR Model Versions: MAE vs Real Indoor Wind Speed", fontsize=14, fontweight="bold")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.show()
"""

# ── Section 8: PINN Comparison ────────────────────────────────────────────────
SEC8_MD = """\
---
## 8  PINN Model Versions vs Real Indoor Wind Speed
"""

SEC8_CODE = """\
fig, axes = plt.subplots(n_sensors, 1, figsize=(14, 4 * n_sensors), sharex=True)
if n_sensors == 1:
    axes = [axes]

for ax, sname in zip(axes, sensor_names):
    for snum in sorted(edf["step_num"].unique()):
        sdf = edf[edf["step_num"] == snum].dropna(subset=[f"pinn_{sname}_mae"])
        if sdf.empty:
            continue
        sdf = sdf.sort_values("eval_dt")
        ax.plot(sdf["eval_dt"], sdf[f"pinn_{sname}_mae"],
                marker="s", ms=4, lw=1.5,
                color=step_color_map.get(snum, "gray"),
                label=f"Step {snum:02d}")

    ax.set_ylabel("MAE (m/s)")
    ax.set_title(f"PINN — sensor: {sname}")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))

axes[0].legend(fontsize=8, loc="upper right")
axes[-1].set_xlabel("Evaluation timestamp (UTC)")
fig.suptitle("PINN Model Versions: MAE vs Real Indoor Wind Speed", fontsize=14, fontweight="bold")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.show()
"""

# ── Section 9: FNO Comparison ─────────────────────────────────────────────────
SEC9_MD = """\
---
## 9  FNO Model Versions vs Real Indoor Wind Speed
"""

SEC9_CODE = """\
fig, axes = plt.subplots(n_sensors, 1, figsize=(14, 4 * n_sensors), sharex=True)
if n_sensors == 1:
    axes = [axes]

for ax, sname in zip(axes, sensor_names):
    for snum in sorted(edf["step_num"].unique()):
        sdf = edf[edf["step_num"] == snum].dropna(subset=[f"fno_{sname}_mae"])
        if sdf.empty:
            continue
        sdf = sdf.sort_values("eval_dt")
        ax.plot(sdf["eval_dt"], sdf[f"fno_{sname}_mae"],
                marker="^", ms=4, lw=1.5,
                color=step_color_map.get(snum, "gray"),
                label=f"Step {snum:02d}")

    ax.set_ylabel("MAE (m/s)")
    ax.set_title(f"FNO — sensor: {sname}")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))

axes[0].legend(fontsize=8, loc="upper right")
axes[-1].set_xlabel("Evaluation timestamp (UTC)")
fig.suptitle("FNO Model Versions: MAE vs Real Indoor Wind Speed", fontsize=14, fontweight="bold")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.show()
"""

# ── Section 10: Combined Group Performance ────────────────────────────────────
SEC10_MD = """\
---
## 10  Combined: Group MAE Over Time & Summary Table

**Left**: Mean MAE across all sensors for each model group (step), aggregated over eval timestamps.
Each step is shown as a bar — lower = better.

**Right**: Summary table — mean/median/min MAE per step per model type.
"""

SEC10_CODE = """\
# ── 10a: Group-level mean MAE bar chart ──────────────────────────────────────
model_types = ["pcr", "pinn", "fno"]
mt_labels   = {"pcr": "PCR", "pinn": "PINN", "fno": "FNO"}
mt_colors   = {"pcr": "#2196F3", "pinn": "#FF9800", "fno": "#4CAF50"}

steps_sorted = sorted(edf["step_num"].unique())
n_steps  = len(steps_sorted)
x        = np.arange(n_steps)
bar_w    = 0.25

fig, ax = plt.subplots(figsize=(14, 5))
for mi, mt in enumerate(model_types):
    means = []
    for snum in steps_sorted:
        sdf = edf[edf["step_num"] == snum]
        cols = [f"{mt}_{sn}_mae" for sn in sensor_names if f"{mt}_{sn}_mae" in sdf.columns]
        vals = sdf[cols].values.flatten()
        vals = vals[~np.isnan(vals)]
        means.append(float(np.mean(vals)) if len(vals) > 0 else np.nan)
    ax.bar(x + mi * bar_w, means, bar_w, label=mt_labels[mt], color=mt_colors[mt], alpha=0.85)

ax.set_xticks(x + bar_w)
ax.set_xticklabels([f"Step {s}" for s in steps_sorted], rotation=30, ha="right")
ax.set_ylabel("Mean MAE (m/s)")
ax.set_title("Mean MAE per Model Group (all sensors averaged)", fontsize=13, fontweight="bold")
ax.legend()
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.show()

# ── 10b: MAE over time — group mean per model type ───────────────────────────
fig, axes = plt.subplots(len(model_types), 1, figsize=(14, 4 * len(model_types)), sharex=True)
for ax, mt in zip(axes, model_types):
    for snum in steps_sorted:
        sdf = edf[edf["step_num"] == snum].sort_values("eval_dt")
        cols = [f"{mt}_{sn}_mae" for sn in sensor_names if f"{mt}_{sn}_mae" in sdf.columns]
        row_means = sdf[cols].mean(axis=1)
        valid = row_means.dropna()
        if valid.empty:
            continue
        ax.plot(sdf.loc[valid.index, "eval_dt"], valid,
                marker="o", ms=3, lw=1.3,
                color=step_color_map.get(snum, "gray"),
                label=f"Step {snum:02d}")
    ax.set_ylabel("Mean MAE (m/s)")
    ax.set_title(f"{mt_labels[mt]} — mean MAE over time")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))

axes[0].legend(fontsize=8, ncol=3, loc="upper right")
axes[-1].set_xlabel("Evaluation timestamp (UTC)")
fig.suptitle("Model Group MAE Over Evaluation Timeline", fontsize=14, fontweight="bold")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.show()

# ── 10c: Summary table ────────────────────────────────────────────────────────
summary_rows = []
for snum in steps_sorted:
    sdf  = edf[edf["step_num"] == snum]
    row  = {"Step": snum}
    if snum in model_store:
        row["Cutoff"] = model_store[snum]["cutoff"].strftime("%m-%d %H:%M")
    for mt in model_types:
        cols = [f"{mt}_{sn}_mae" for sn in sensor_names if f"{mt}_{sn}_mae" in sdf.columns]
        vals = sdf[cols].values.flatten()
        vals = vals[~np.isnan(vals)]
        row[f"{mt_labels[mt]} MAE mean"] = round(float(np.mean(vals)), 4) if len(vals) else np.nan
        row[f"{mt_labels[mt]} MAE min"]  = round(float(np.min(vals)), 4)  if len(vals) else np.nan
    summary_rows.append(row)

sdf_summary = pd.DataFrame(summary_rows).set_index("Step")

def _color_col(s):
    valid = s.dropna()
    if valid.empty:
        return [""] * len(s)
    mn, mx = valid.min(), valid.max()
    def _c(v):
        if pd.isna(v): return ""
        t = (v - mn) / (mx - mn + 1e-12)
        r = int(255 * t); g = int(255 * (1 - t))
        return f"background-color: rgb({r},{g},100)"
    return [_c(v) for v in s]

mean_cols = [c for c in sdf_summary.columns if "mean" in c]
display(sdf_summary.style.apply(_color_col, subset=mean_cols)
        .set_caption("Summary: Mean & Min MAE per Step per Model Type (green = lower = better)")
        .format(na_rep="—"))
"""

# Build new cells list
new_cells = [
    md(SEC3_MD),  code(SEC3_CODE),
    md(SEC4_MD),  code(SEC4_CODE),
    md(SEC5_MD),  code(SEC5_CODE),
    md(SEC6_MD),  code(SEC6_CODE),
    md(SEC7_MD),  code(SEC7_CODE),
    md(SEC8_MD),  code(SEC8_CODE),
    md(SEC9_MD),  code(SEC9_CODE),
    md(SEC10_MD), code(SEC10_CODE),
]

nb["cells"].extend(new_cells)

with open(NB_PATH, "w") as f:
    json.dump(nb, f, indent=1)

print(f"Done. Notebook now has {len(nb['cells'])} cells.")
