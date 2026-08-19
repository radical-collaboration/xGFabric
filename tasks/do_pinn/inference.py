import json

import logging
import numpy as np
import tensorflow as tf
from .MPWB2 import PhysicsMLP3D

# Global config vals:
x_min, x_max = 8.3, 176.5  # Based on the CFD domain bounds
y_min, y_max = 8.1, 82.1  # Based on the CFD domain bounds
z_min, z_max = 0.5, 5.0  # 0.5m from ground, 0.5m from roof (5.5m structure height)


def prepare(model_weights, model_meta, logger: logging.Logger):
    with open(model_meta) as f:
        pinn_meta = json.load(f)

    pinn = PhysicsMLP3D(hidden=pinn_meta["hidden"], n_layers=pinn_meta["n_layers"])
    _ = pinn(tf.zeros((1, 4)))  # build all layers

    # Force-build every block in the list (ensures Keras tracks them before loading)
    for blk in pinn.blocks:
        if not blk.built:
            blk.build((None, pinn_meta["hidden"]))

    pinn.load_weights(model_weights)

    n_pinn = sum(np.prod(v.shape) for v in pinn.trainable_variables)
    logger.info(f"PINN loaded  ({n_pinn:,} params)")
    logger.info(
        f'  best_val_mse = {pinn_meta["best_val_mse"]:.5f}  '
        f'epochs = {pinn_meta["epochs_trained"]}'
    )

    return pinn, pinn_meta


def pinn_predict_field(pinn, pinn_meta, pts, ws: float, z: float):
    PINN_VEL_MAX = pinn_meta["VEL_MAX"]
    PINN_WS_MAX = pinn_meta["WS_MAX"]

    xg, yg = pts

    x_n = ((xg.ravel() - x_min) / (x_max - x_min + 1e-12)).astype(np.float32)
    y_n = ((yg.ravel() - y_min) / (y_max - y_min + 1e-12)).astype(np.float32)

    ws_n = float(ws / (PINN_WS_MAX + 1e-8))
    z_n = float((z - z_min) / (z_max - z_min + 1e-12))

    inp = np.column_stack([x_n, y_n, np.full_like(x_n, z_n), np.full_like(x_n, ws_n)])
    pred = pinn(tf.constant(inp, dtype=tf.float32), training=False).numpy()
    u_ms = pred[:, 0] * PINN_VEL_MAX
    v_ms = pred[:, 1] * PINN_VEL_MAX
    # xg.shape is the same as the Y,X size of pts. (repeats 'X' Y times)
    # reshape into Y, X
    spd = np.sqrt(u_ms**2 + v_ms**2).reshape(xg.shape[0], xg.shape[1])
    return spd


def graph(data, fname, z, w):
    import matplotlib.pyplot as plt

    plt.figure(figsize=(6, 5))

    # Plot heatmap
    im = plt.imshow(data, cmap="viridis", origin="lower", vmin=0, vmax=4)

    # Add colorbar
    plt.colorbar(im)

    # Optional labels
    plt.title(f"Heatmap of PI at Z={z}, W={round(w,3)}")
    plt.xlabel("X")
    plt.ylabel("Y")

    # Save image
    plt.savefig(fname, dpi=300, bbox_inches="tight")

    plt.close()
