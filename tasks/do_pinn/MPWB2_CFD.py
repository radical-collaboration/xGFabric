"""
PINN implementation for CFD data processing and training.
Uses PhysicsMLP3D: 4-input (x,y,z,ws) model with skip connections and 3D physics.
Ported from explore_pinn.ipynb where this architecture trained successfully.

Key design choices (matching notebook):
  - 4 inputs: (x_norm, y_norm, z_norm, ws_norm) — not 2D
  - Global VEL_MAX normalization across all wind speeds
  - Zero-velocity filtering (removes stagnation/solid points)
  - Skip (residual) connections with tanh activation
  - 3D Navier-Stokes physics loss (includes z-derivatives)
  - Batched training with CosineDecay LR schedule
  - alpha=0.07 physics weight (not 0.5) — data-dominant
  - Patience=60 on validation data loss (not direction error)
"""

from dataclasses import dataclass
import logging
import numpy as np
import tensorflow as tf
import pandas as pd
import random
import os
import json
import gc
from sklearn.model_selection import train_test_split

from .MPWB2 import PhysicsMLP3D, normalize
from ..common.cfd_common import (
    x_min,
    x_max,
    y_min,
    y_max,
    z_min,
    z_max,
    Lx,
    Ly,
    Lz,
    filter_spatial_bounds,
    filter_zero_velocity,
    expand_to_df,
)

# -----------------------------
# Reproducibility
# -----------------------------
np.random.seed(42)
random.seed(42)
tf.random.set_seed(42)


# ---------------------------------------------------------------------------
# 3D Physics Loss  (matches explore_pinn.ipynb  compute_physics_loss_3d)
# ---------------------------------------------------------------------------
def compute_physics_loss_3d(
    model, x_c, y_c, z_c, ws_c, domain_Lx, domain_Ly, domain_Lz, nu, w_div=1.0
):
    """
    3D steady-state Navier-Stokes residuals at collocation points.

    Momentum (no pressure, steady state):
        u*du/dx + v*du/dy  =  nu*(d2u/dx2 + d2u/dy2 + d2u/dz2)
        u*dv/dx + v*dv/dy  =  nu*(d2v/dx2 + d2v/dy2 + d2v/dz2)
    Continuity:
        du/dx + dv/dy = 0

    Returns: (total_physics_loss, pde_loss, div_loss)
    """
    invLx = 1.0 / domain_Lx
    invLy = 1.0 / domain_Ly
    invLz = 1.0 / domain_Lz

    with tf.GradientTape(persistent=True) as tape2:
        tape2.watch([x_c, y_c, z_c])
        with tf.GradientTape(persistent=True) as tape1:
            tape1.watch([x_c, y_c, z_c])
            inp = tf.concat([x_c, y_c, z_c, ws_c], axis=1)
            uv = model(inp, training=True)
            Uc = uv[:, 0:1]
            Vc = uv[:, 1:2]

        # First derivatives (normalised coords)
        U_xn = tape1.gradient(Uc, x_c)
        U_yn = tape1.gradient(Uc, y_c)
        U_zn = tape1.gradient(Uc, z_c)
        V_xn = tape1.gradient(Vc, x_c)
        V_yn = tape1.gradient(Vc, y_c)
        V_zn = tape1.gradient(Vc, z_c)

    # Second derivatives (normalised coords)
    U_xxn = tape2.gradient(U_xn, x_c)
    U_yyn = tape2.gradient(U_yn, y_c)
    U_zzn = tape2.gradient(U_zn, z_c)
    V_xxn = tape2.gradient(V_xn, x_c)
    V_yyn = tape2.gradient(V_yn, y_c)
    V_zzn = tape2.gradient(V_zn, z_c)

    del tape1, tape2

    # Chain rule -> physical derivatives
    Ux, Uy = U_xn * invLx, U_yn * invLy
    Vx, Vy = V_xn * invLx, V_yn * invLy
    Uxx, Uyy, Uzz = U_xxn * invLx**2, U_yyn * invLy**2, U_zzn * invLz**2
    Vxx, Vyy, Vzz = V_xxn * invLx**2, V_yyn * invLy**2, V_zzn * invLz**2

    # Steady 3D NS residuals (convection = diffusion)
    f_u = Uc * Ux + Vc * Uy - nu * (Uxx + Uyy + Uzz)
    f_v = Uc * Vx + Vc * Vy - nu * (Vxx + Vyy + Vzz)

    # Incompressibility
    div = Ux + Vy

    pde_loss = tf.reduce_mean(tf.square(f_u)) + tf.reduce_mean(tf.square(f_v))
    div_loss = tf.reduce_mean(tf.square(div))
    total = pde_loss + w_div * div_loss

    return total, pde_loss, div_loss


# ---------------------------------------------------------------------------
# Data preparation  (matches notebook Cell 2 + Cell 3)
# ---------------------------------------------------------------------------
def prepare_data_3d(
    data_list,
    logger,
    max_points_per_file=5000,
    umag_min=0.0,
    test_size=0.20,
    val_size=0.10,
):
    """
    Load, filter, normalise and split CFD data -- matching the notebook pipeline.

    Steps:
      1. Spatial bounds filter  (x, y, z)
      2. Zero-velocity filter   (|U| > umag_min)
      3. Random subsample       (max_points_per_file per file)
      4. Global VEL_MAX norm    (single scale across ALL wind speeds)
      5. Stratified train/val/test split by wind speed

    Returns dict with keys: train, val, test, VEL_MAX, WS_MAX
    Each split has: X  (N,4)  [x_norm, y_norm, z_norm, ws_norm]
                    Y  (N,2)  [u_norm, v_norm]
    """
    log = logger.info

    raw_x, raw_y, raw_z = [], [], []
    raw_u, raw_v = [], []
    all_ws = []

    for ws, df in data_list:
        # 1. Spatial bounds
        df_f = filter_spatial_bounds(df)
        n_spatial = len(df_f)

        # 2. Remove zero / near-zero velocity
        df_f = filter_zero_velocity(df_f, umag_min=umag_min)
        n_clean = len(df_f)

        # 3. Random subsample
        if len(df_f) > max_points_per_file:
            df_f = df_f.sample(n=max_points_per_file, random_state=42)

        # Normalise coords
        x_n = (
            normalize(df_f["x"].values, x_min, x_max).astype(np.float32).reshape(-1, 1)
        )
        y_n = (
            normalize(df_f["y"].values, y_min, y_max).astype(np.float32).reshape(-1, 1)
        )
        z_n = (
            ((df_f["z"].values - z_min) / (z_max - z_min + 1e-12))
            .astype(np.float32)
            .reshape(-1, 1)
        )

        raw_x.append(x_n)
        raw_y.append(y_n)
        raw_z.append(z_n)
        raw_u.append(df_f["U_0"].values.astype(np.float32).reshape(-1, 1))
        raw_v.append(df_f["U_1"].values.astype(np.float32).reshape(-1, 1))
        all_ws.extend([ws] * len(df_f))

        log(
            f"  ws={ws:6.2f}  spatial={n_spatial:>8,}  after |U|>=0={n_clean:>8,} "
            f"(removed {n_spatial - n_clean:,})  sampled={len(df_f):>5,}"
        )

        if len(df_f) == 0:
            log(f"  ws={ws:6.2f}  SKIPPED — no points survive velocity filter")
            del df_f
            gc.collect()
            continue

        del df_f
        gc.collect()

    if not raw_u:
        raise RuntimeError(
            "No usable data after velocity filtering across all files. "
            "Check that CSV velocity columns match expectations and that "
            "--umag_min is appropriate for your data units."
        )

    X_coord = np.concatenate(raw_x)
    Y_coord = np.concatenate(raw_y)
    Z_coord = np.concatenate(raw_z)
    U_raw = np.concatenate(raw_u)
    V_raw = np.concatenate(raw_v)
    WS_arr = np.array(all_ws, dtype=np.float32)

    # Global velocity normalisation
    VEL_MAX = float(np.maximum(np.abs(U_raw).max(), np.abs(V_raw).max()))
    U_norm = U_raw / (VEL_MAX + 1e-8)
    V_norm = V_raw / (VEL_MAX + 1e-8)

    WS_MAX = float(WS_arr.max())
    WS_norm = (WS_arr / (WS_MAX + 1e-8)).reshape(-1, 1).astype(np.float32)

    # Build feature / target arrays
    X_in = np.concatenate([X_coord, Y_coord, Z_coord, WS_norm], axis=1)  # (N,4)
    Y_out = np.concatenate([U_norm, V_norm], axis=1)  # (N,2)

    log(
        f"Total points: {len(X_in):,}  VEL_MAX={VEL_MAX:.4f} m/s  WS_MAX={WS_MAX:.2f} m/s"
    )

    # Stratified split by wind speed
    idx = np.arange(len(X_in))
    train_val_idx, test_idx = train_test_split(
        idx, test_size=test_size, random_state=42, stratify=WS_arr
    )
    train_idx, val_idx = train_test_split(
        train_val_idx,
        test_size=val_size / (1 - test_size),
        random_state=42,
        stratify=WS_arr[train_val_idx],
    )

    splits = {}
    for name, idxs in [("train", train_idx), ("val", val_idx), ("test", test_idx)]:
        splits[name] = {"X": X_in[idxs], "Y": Y_out[idxs]}
        log(f"  {name:>5s}: {len(idxs):>6,} samples")

    splits["VEL_MAX"] = VEL_MAX
    splits["WS_MAX"] = WS_MAX
    return splits


@dataclass
class PINN_Config:
    # Max random points to sample per wind-speed CSV file
    # (corresponds to --max_points_per_file)
    max_points_per_file = 5000
    # Drop points with |U| <= this (default 0.0 keeps all)
    # (corresponds to --umag_min)
    umag_min = 0.0
    # Fraction of data reserved for the test set
    # (corresponds to --test_size)
    test_size = 0.15
    # Fraction of the training+validation split used for validation
    # (corresponds to --val_size)
    val_size = 0.10
    # Number of collocation points used for the physics loss
    # (corresponds to --cpoints)
    cpoints = 500
    # Physics weight: proportion of total loss coming from physics
    # (e.g. 0.07 means ~7% physics, 93% data) (corresponds to --alpha)
    alpha = 0.07
    # Hidden layer width for the MLP (corresponds to --hidden)
    hidden = 128
    # Number of residual blocks / hidden layers (corresponds to --n_layers)
    n_layers = 4
    # Path to pretrained weights for fine-tuning (corresponds to --init_weights)
    init_weights = None
    # Training batch size (corresponds to --batch_size)
    batch_size = 512
    # Number of training epochs (corresponds to --epochs)
    epochs = 5
    # Initial learning rate for the optimizer (CosineDecay schedule)
    # (corresponds to --learning_rate)
    learning_rate = 1e-4
    # Viscosity-like term used in physics loss (corresponds to --nu)
    nu = 0.01
    # Weight applied to the divergence loss term (corresponds to --w_div)
    w_div = 1.0
    # Gradient clipping global norm value (if used; referenced as --clip_value)
    clip_value = 1.0
    # Early stopping patience on validation loss (corresponds to --patience)
    patience = 3


def pinn_main_entry(
    simulation_data_list, output_directory, pinn_config: PINN_Config, logger
):
    # expand each csv into dataframes

    data_list = []
    for wind_speed, simulation_csv in simulation_data_list:
        _, df = expand_to_df(wind_speed, simulation_csv)
        if df is None:
            continue
        data_list.append((wind_speed, df))

    # ---- Prepare data (filter, normalise, split) ----
    try:
        splits = prepare_data_3d(
            data_list,
            logger,
            max_points_per_file=pinn_config.max_points_per_file,
            umag_min=pinn_config.umag_min,
            test_size=pinn_config.test_size,
            val_size=pinn_config.val_size,
        )
    except RuntimeError as exc:
        logger.error(f"Training aborted — no data to train on. {exc}")
        return

    VEL_MAX = splits["VEL_MAX"]
    WS_MAX = splits["WS_MAX"]
    X_train, Y_train = splits["train"]["X"], splits["train"]["Y"]
    X_val, Y_val = splits["val"]["X"], splits["val"]["Y"]
    X_test, Y_test = splits["test"]["X"], splits["test"]["Y"]

    # ---- Collocation points: (x, y, z) in [0,1], ws sampled from training ----
    np.random.seed(42)
    x_coll = np.random.uniform(0, 1, (pinn_config.cpoints, 1)).astype(np.float32)
    y_coll = np.random.uniform(0, 1, (pinn_config.cpoints, 1)).astype(np.float32)
    z_coll = np.random.uniform(0, 1, (pinn_config.cpoints, 1)).astype(np.float32)
    # Sample ws from training data's unique wind speeds
    unique_ws_norm = np.unique(X_train[:, 3])
    ws_coll = (
        np.random.choice(unique_ws_norm, size=pinn_config.cpoints)
        .reshape(-1, 1)
        .astype(np.float32)
    )

    logger.info(f"Collocation: {pinn_config.cpoints} points in (x, y, z, ws)")
    logger.info(f"Physics weight alpha = {pinn_config.alpha}")

    # ---- Build model ----
    model = PhysicsMLP3D(hidden=pinn_config.hidden, n_layers=pinn_config.n_layers)
    _ = model(tf.zeros((1, 4)))  # build
    n_params = sum(p.numpy().size for p in model.trainable_variables)
    logger.info(
        f"PhysicsMLP3D: {n_params:,} parameters  "
        f"({pinn_config.n_layers} blocks x {pinn_config.hidden} hidden, tanh, skip connections)"
    )

    # ---- Load pretrained weights ----
    if pinn_config.init_weights and os.path.exists(pinn_config.init_weights):
        try:
            model.load_weights(pinn_config.init_weights)
            logger.info(f"Loaded pretrained weights from: {pinn_config.init_weights}")
        except Exception as e:
            logger.warning(f"Failed to load pretrained weights: {e}")

    # ---- Optimizer with CosineDecay LR ----
    n_batches = len(X_train) // pinn_config.batch_size + 1
    lr_schedule = tf.keras.optimizers.schedules.CosineDecay(
        pinn_config.learning_rate, decay_steps=pinn_config.epochs * n_batches
    )
    opt = tf.keras.optimizers.Adam(learning_rate=lr_schedule)
    loss_fn = tf.keras.losses.MeanSquaredError()

    # ---- tf.data datasets ----
    ds_train = (
        tf.data.Dataset.from_tensor_slices((X_train, Y_train))
        .shuffle(len(X_train), seed=42)
        .batch(pinn_config.batch_size)
        .prefetch(tf.data.AUTOTUNE)
    )
    ds_val = tf.data.Dataset.from_tensor_slices((X_val, Y_val)).batch(
        pinn_config.batch_size
    )

    # ---- Collocation tensors ----
    xc = tf.Variable(x_coll, trainable=False)
    yc = tf.Variable(y_coll, trainable=False)
    zc = tf.Variable(z_coll, trainable=False)
    wsc = tf.constant(ws_coll, dtype=tf.float32)

    # ---- Training loop ----
    hist = {
        "epoch": [],
        "train_loss": [],
        "val_loss": [],
        "data_loss": [],
        "phys_loss": [],
        "div_loss": [],
    }
    best_val = float("inf")
    patience_counter = 0
    best_weights = None

    logger.info(f"\nTraining PhysicsMLP3D for up to {pinn_config.epochs} epochs ...")

    for ep in range(pinn_config.epochs):
        batch_loss_sum = tf.constant(0.0)
        n_batches = 0
        for xb, yb in ds_train:
            with tf.GradientTape() as tape:
                pred = model(xb, training=True)
                data_loss = loss_fn(yb, pred)

                phys_total, l_pde, l_div = compute_physics_loss_3d(
                    model,
                    xc,
                    yc,
                    zc,
                    wsc,
                    Lx,
                    Ly,
                    Lz,
                    pinn_config.nu,
                    pinn_config.w_div,
                )

                total_loss = (
                    1.0 - pinn_config.alpha
                ) * data_loss + pinn_config.alpha * phys_total

            grads = tape.gradient(total_loss, model.trainable_variables)
            clipped, _ = tf.clip_by_global_norm(grads, pinn_config.clip_value)
            opt.apply_gradients(zip(clipped, model.trainable_variables))
            batch_loss_sum = batch_loss_sum + total_loss
            n_batches += 1

        avg_train = float(batch_loss_sum) / max(n_batches, 1)

        # Validation
        val_loss_sum = tf.constant(0.0)
        n_val = 0
        for xb, yb in ds_val:
            pred_v = model(xb, training=False)
            val_loss_sum = val_loss_sum + loss_fn(yb, pred_v)
            n_val += 1
        avg_val = float(val_loss_sum) / max(n_val, 1)

        # Log every 10 epochs
        if ep % 10 == 0 or ep == pinn_config.epochs - 1:
            hist["epoch"].append(ep)
            hist["train_loss"].append(avg_train)
            hist["val_loss"].append(avg_val)
            hist["data_loss"].append(float(data_loss))
            hist["phys_loss"].append(float(l_pde))
            hist["div_loss"].append(float(l_div))
            logger.info(
                f"Epoch {ep:>4d}: train={avg_train:.4e}  val={avg_val:.4e}  "
                f"phys={float(phys_total):.2e}  div={float(l_div):.2e}  "
                f"best={best_val:.4e}  pat={patience_counter}/{pinn_config.patience}"
            )

        # Early stopping on val loss
        if avg_val < best_val:
            best_val = avg_val
            patience_counter = 0
            best_weights = model.get_weights()
        else:
            patience_counter += 1

        if patience_counter >= pinn_config.patience:
            logger.info(f"Early stopping at epoch {ep}")
            break

    # Restore best weights
    if best_weights is not None:
        model.set_weights(best_weights)
    epochs_trained = ep + 1

    # ---- Save model ----
    model_path = os.path.join(output_directory, f"pinn.weights.h5")
    model.save_weights(model_path)

    # Normalization metadata
    norm_meta = {
        "x_min": float(x_min),
        "x_max": float(x_max),
        "y_min": float(y_min),
        "y_max": float(y_max),
        "z_min": float(z_min),
        "z_max": float(z_max),
        "VEL_MAX": VEL_MAX,
        "WS_MAX": WS_MAX,
        "Lx": float(Lx),
        "Ly": float(Ly),
        "Lz": float(Lz),
    }
    norm_path = os.path.join(output_directory, f"pinn.normalization.json")
    with open(norm_path, "w") as f:
        json.dump(norm_meta, f, indent=2)

    # Run configuration
    run_path = os.path.join(output_directory, f"pinn.run.json")
    with open(run_path, "w") as f:
        json.dump(vars(pinn_config), f, indent=2, default=str)

    # Model metadata
    model_meta = {
        "model_type": "PINN",
        "model_class": "PhysicsMLP3D",
        "input_dim": 4,
        "input_names": ["x_norm", "y_norm", "z_norm", "ws_norm"],
        "n_hidden_layers": pinn_config.n_layers,
        "hidden_dim": pinn_config.hidden,
        "activation": "tanh",
        "skip_connections": True,
        "output_dim": 2,
        "output_names": ["u_norm", "v_norm"],
        "output_units": "normalised (multiply by VEL_MAX for m/s)",
        "x_min": float(x_min),
        "x_max": float(x_max),
        "y_min": float(y_min),
        "y_max": float(y_max),
        "z_min": float(z_min),
        "z_max": float(z_max),
        "VEL_MAX": VEL_MAX,
        "WS_MAX": WS_MAX,
        "best_val_loss": float(best_val),
        "epochs_trained": epochs_trained,
        "alpha": pinn_config.alpha,
        "ws_conditioned": True,
        "z_conditioned": True,
    }
    meta_path = os.path.join(output_directory, f"pinn.model_meta.json")
    with open(meta_path, "w") as f:
        json.dump(model_meta, f, indent=2)
    logger.info(f"Model meta saved -> {meta_path}")

    # ---- Final evaluation ----
    pred_test = model(tf.constant(X_test, dtype=tf.float32), training=False).numpy()
    u_pred = pred_test[:, 0:1] * VEL_MAX
    v_pred = pred_test[:, 1:2] * VEL_MAX
    u_true = Y_test[:, 0:1] * VEL_MAX
    v_true = Y_test[:, 1:2] * VEL_MAX
    spd_pred = np.sqrt(u_pred**2 + v_pred**2)
    spd_true = np.sqrt(u_true**2 + v_true**2)

    rmse_u = np.sqrt(np.mean((u_pred - u_true) ** 2))
    rmse_v = np.sqrt(np.mean((v_pred - v_true) ** 2))
    rmse_spd = np.sqrt(np.mean((spd_pred - spd_true) ** 2))

    logger.info("=== Final Test Results ===")
    logger.info(f"RMSE_u: {rmse_u:.3f} m/s")
    logger.info(f"RMSE_v: {rmse_v:.3f} m/s")
    logger.info(f"RMSE_speed: {rmse_spd:.3f} m/s")
    logger.info(f"Model saved to {model_path}")

    # Save training history
    hist_path = os.path.join(output_directory, "training_history.csv")
    pd.DataFrame(hist).to_csv(hist_path, index=False)
    logger.info(f"Training history saved -> {hist_path}")
