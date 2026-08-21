import json

import logging
import numpy as np
import tensorflow as tf
from scipy.interpolate import RegularGridInterpolator
from .train_fno import *

# Global config vals:
x_min, x_max = 8.3, 176.5  # Based on the CFD domain bounds
y_min, y_max = 8.1, 82.1  # Based on the CFD domain bounds
z_min, z_max = 0.5, 5.0  # 0.5m from ground, 0.5m from roof (5.5m structure height)


def prepare(model_weights, model_meta, logger: logging.Logger):
    with open(model_meta) as f:
        fno_meta = json.load(f)

    FNO_VEL_MAX = fno_meta["VEL_MAX"]
    FNO_WS_MAX = fno_meta["WS_MAX"]
    FNO_NX = fno_meta["NX"]
    FNO_NY = fno_meta["NY"]
    FNO_IN_CH = fno_meta["in_ch"]
    FNO_HIDDEN = fno_meta["hidden"]
    FNO_NLAYERS = fno_meta["n_layers"]
    FNO_MODES1 = fno_meta["modes1"]
    FNO_MODES2 = fno_meta["modes2"]

    logger.info(f"TF version  : {tf.__version__}")
    logger.info(
        f"FNO grid    : {FNO_NX}×{FNO_NY}  VEL_MAX={FNO_VEL_MAX:.4f}  WS_MAX={FNO_WS_MAX}"
    )
    logger.info("✓ Imports OK")

    # Load Model

    fno = FNO2D(
        in_ch=FNO_IN_CH,
        out_ch=2,
        hidden=FNO_HIDDEN,
        n_layers=FNO_NLAYERS,
        modes1=FNO_MODES1,
        modes2=FNO_MODES2,
        name="fno2d",
    )

    _dummy = np.zeros((1, FNO_NX, FNO_NY, FNO_IN_CH), dtype=np.float32)
    _ = fno(_dummy)  # build weights
    fno.load_weights(model_weights)

    n_params = sum(np.prod(v.shape) for v in fno.trainable_variables)
    logger.info(f"FNO2D loaded  ({n_params:,} params)")
    logger.info(
        f'  best_val_mse = {fno_meta["best_val_mse"]:.5f}  '
        f'epochs = {fno_meta["epochs_trained"]}'
    )
    logger.info("✓ FNO2D ready")
    return fno, fno_meta


def precompute_static(fno_meta):
    FNO_NX = fno_meta["NX"]
    FNO_NY = fno_meta["NY"]
    _x_lin = np.linspace(x_min, x_max, FNO_NX)
    _y_lin = np.linspace(y_min, y_max, FNO_NY)
    _xx, _yy = np.meshgrid(_x_lin, _y_lin, indexing="ij")  # (NX, NY)

    x_norm_grid = ((_xx - x_min) / (x_max - x_min + 1e-12)).astype(np.float32)
    y_norm_grid = ((_yy - y_min) / (y_max - y_min + 1e-12)).astype(np.float32)

    return x_norm_grid, y_norm_grid, _x_lin, _y_lin


def sinusoidal_embed(param_val, x_grid, y_grid, L):
    """Amplitude-modulated sinusoidal embedding  →  (NX, NY, 4*L)."""
    channels = []
    for k in range(1, L + 1):
        channels.append((param_val * np.sin(k * 2 * np.pi * x_grid)).astype(np.float32))
        channels.append((param_val * np.cos(k * 2 * np.pi * x_grid)).astype(np.float32))
        channels.append((param_val * np.sin(k * 2 * np.pi * y_grid)).astype(np.float32))
        channels.append((param_val * np.cos(k * 2 * np.pi * y_grid)).astype(np.float32))
    return np.stack(channels, axis=-1)


def fno_predict_field(
    fno, fno_meta, x_norm_grid, y_norm_grid, x_lin, y_lin, pts, ws: float, z: float
):
    """
    Run FNO2D inference at a single (ws, z) operating point.
    Returns speed field  (FNO_NX, FNO_NY)  in m/s.
    """
    FNO_VEL_MAX = fno_meta["VEL_MAX"]
    FNO_WS_MAX = fno_meta["WS_MAX"]
    FNO_EMBED_L = fno_meta["embed_L"]

    ws_n = float(ws / (FNO_WS_MAX + 1e-8))
    z_n = float((z - z_min) / (z_max - z_min + 1e-12))

    ws_embed = sinusoidal_embed(ws_n, x_norm_grid, y_norm_grid, FNO_EMBED_L)
    z_embed = sinusoidal_embed(z_n, x_norm_grid, y_norm_grid, FNO_EMBED_L)

    inp = np.concatenate(
        [
            x_norm_grid[..., np.newaxis],
            y_norm_grid[..., np.newaxis],
            ws_embed,
            z_embed,
        ],
        axis=-1,
    )[
        np.newaxis
    ]  # (1, NX, NY, IN_CH)

    pred = fno(tf.constant(inp, dtype=tf.float32), training=False).numpy()[
        0
    ]  # (NX, NY, 2)
    u_ms = pred[..., 0] * FNO_VEL_MAX
    v_ms = pred[..., 1] * FNO_VEL_MAX
    speed_field = np.sqrt(u_ms**2 + v_ms**2)  # (NX, NY)

    # FNO returns points in the (NX, NY) coordinate system.
    # We want the actual scale of the farm (meters by meters)
    # Scale out then to the farm dimensions.
    interp = RegularGridInterpolator(
        (x_lin, y_lin),
        speed_field,
        method="linear",
        bounds_error=False,
        fill_value=np.nan,
    )

    return interp((pts[0], pts[1]))


def graph(data, fname, z, w):
    import matplotlib.pyplot as plt

    plt.figure(figsize=(6, 5))

    # Plot heatmap
    im = plt.imshow(data, cmap="viridis", origin="lower", vmin=0, vmax=2.5)

    # Add colorbar
    plt.colorbar(im)

    # Optional labels
    plt.title(f"Heatmap of FNO at Z={z}, W={round(w,3)}")
    plt.xlabel("X")
    plt.ylabel("Y")

    # Save image
    plt.savefig(fname, dpi=300, bbox_inches="tight")

    plt.close()
