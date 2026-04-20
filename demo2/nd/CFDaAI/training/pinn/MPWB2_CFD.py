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
import numpy as np
import tensorflow as tf
import pandas as pd
from datetime import datetime
import random
import argparse
import logging
import os
import sys
import json
import gc
from sklearn.model_selection import train_test_split

# Add training directory to path for shared utilities
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from MPWB2 import PhysicsMLP3D, setup_logger, normalize
from cfd_common import (
    x_min, x_max, y_min, y_max, z_min, z_max,
    Lx, Ly, Lz,
    filter_spatial_bounds,
    filter_zero_velocity,
    read_cfd_data,
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
def compute_physics_loss_3d(model, x_c, y_c, z_c, ws_c,
                            domain_Lx, domain_Ly, domain_Lz, nu, w_div=1.0):
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
def prepare_data_3d(data_list, max_points_per_file=5000, umag_min=0.10,
                    test_size=0.20, val_size=0.10, logger=None):
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
    log = logger.info if logger else print

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
        x_n = normalize(df_f['x'].values, x_min, x_max).astype(np.float32).reshape(-1, 1)
        y_n = normalize(df_f['y'].values, y_min, y_max).astype(np.float32).reshape(-1, 1)
        z_n = ((df_f['z'].values - z_min) / (z_max - z_min + 1e-12)).astype(np.float32).reshape(-1, 1)

        raw_x.append(x_n)
        raw_y.append(y_n)
        raw_z.append(z_n)
        raw_u.append(df_f['U_0'].values.astype(np.float32).reshape(-1, 1))
        raw_v.append(df_f['U_1'].values.astype(np.float32).reshape(-1, 1))
        all_ws.extend([ws] * len(df_f))

        log(f"  ws={ws:6.2f}  spatial={n_spatial:>8,}  after |U|>{umag_min}={n_clean:>8,} "
            f"(removed {n_spatial - n_clean:,})  sampled={len(df_f):>5,}")

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
    U_raw   = np.concatenate(raw_u)
    V_raw   = np.concatenate(raw_v)
    WS_arr  = np.array(all_ws, dtype=np.float32)

    # Global velocity normalisation
    VEL_MAX = float(np.maximum(np.abs(U_raw).max(), np.abs(V_raw).max()))
    U_norm = U_raw / (VEL_MAX + 1e-8)
    V_norm = V_raw / (VEL_MAX + 1e-8)

    WS_MAX = float(WS_arr.max())
    WS_norm = (WS_arr / (WS_MAX + 1e-8)).reshape(-1, 1).astype(np.float32)

    # Build feature / target arrays
    X_in  = np.concatenate([X_coord, Y_coord, Z_coord, WS_norm], axis=1)   # (N,4)
    Y_out = np.concatenate([U_norm, V_norm], axis=1)                        # (N,2)

    log(f"Total points: {len(X_in):,}  VEL_MAX={VEL_MAX:.4f} m/s  WS_MAX={WS_MAX:.2f} m/s")

    # Stratified split by wind speed
    idx = np.arange(len(X_in))
    train_val_idx, test_idx = train_test_split(
        idx, test_size=test_size, random_state=42, stratify=WS_arr)
    train_idx, val_idx = train_test_split(
        train_val_idx, test_size=val_size / (1 - test_size),
        random_state=42, stratify=WS_arr[train_val_idx])

    splits = {}
    for name, idxs in [('train', train_idx), ('val', val_idx), ('test', test_idx)]:
        splits[name] = {'X': X_in[idxs], 'Y': Y_out[idxs]}
        log(f"  {name:>5s}: {len(idxs):>6,} samples")

    splits['VEL_MAX'] = VEL_MAX
    splits['WS_MAX']  = WS_MAX
    return splits


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='PINN for 3D CFD data (PhysicsMLP3D)')
    parser.add_argument('input', help='CFD data CSV file or directory')
    parser.add_argument('model_fname', help='Model save name')
    parser.add_argument('--epochs', '-e', type=int, default=200)
    parser.add_argument('--batch_size', type=int, default=512)
    parser.add_argument('--cpoints', '-c', type=int, default=2000,
                        help='Collocation points for physics loss')
    parser.add_argument('--nu', type=float, default=0.01, help='Viscosity-like term')
    parser.add_argument('--alpha', type=float, default=0.07,
                        help='Physics weight (0.07 = 7%% physics, 93%% data)')
    parser.add_argument('--w_div', type=float, default=1.0, help='Divergence weight')
    parser.add_argument('--test_size', type=float, default=0.20)
    parser.add_argument('--val_size', type=float, default=0.10)
    parser.add_argument('--learning_rate', type=float, default=2e-3,
                        help='Initial learning rate (CosineDecay)')
    parser.add_argument('--patience', type=int, default=60,
                        help='Early stopping patience on val loss')
    parser.add_argument('--clip_value', type=float, default=1.0)
    parser.add_argument('--hidden', type=int, default=128,
                        help='Hidden layer width')
    parser.add_argument('--n_layers', type=int, default=4,
                        help='Number of residual blocks')
    parser.add_argument('--max_points_per_file', type=int, default=5000,
                        help='Max random points per wind-speed file')
    parser.add_argument('--umag_min', type=float, default=0.10,
                        help='Drop points with |U| <= this (stagnation/solids)')
    parser.add_argument('--init_weights', type=str, default=None,
                        help='Pretrained weights for fine-tuning')
    parser.add_argument('--output_dir', type=str, default=None)
    # Keep --subsample for backward compat but secondary to max_points_per_file
    parser.add_argument('--subsample', type=int, default=1,
                        help='Subsample factor (default: 1 = no subsampling)')

    args = parser.parse_args()

    # ---- Output directory ----
    if args.output_dir:
        experiment_dir = args.output_dir
    else:
        timestamp = datetime.now().strftime('%m-%d-%H-%M-%S')
        experiment_dir = f'experiment_cfd_{timestamp}'
    os.makedirs(experiment_dir, exist_ok=True)
    logger = setup_logger(experiment_dir)

    # ---- Load CFD data ----
    data_list = read_cfd_data(args.input)
    logger.info(f"Loaded {len(data_list)} data files")
    logger.info(f"Domain bounds: x=[{x_min:.1f},{x_max:.1f}] y=[{y_min:.1f},{y_max:.1f}] "
                f"z=[{z_min:.1f},{z_max:.1f}] m")

    # Optional legacy subsampling (before the smarter per-file cap)
    if args.subsample > 1:
        logger.info(f"Subsampling data by factor of {args.subsample}")
        subsampled = []
        for ws, df in data_list:
            df_sub = df.iloc[::args.subsample].reset_index(drop=True)
            logger.info(f"  ws={ws}: {len(df)} -> {len(df_sub)}")
            subsampled.append((ws, df_sub))
        data_list = subsampled

    # ---- Prepare data (filter, normalise, split) ----
    try:
        splits = prepare_data_3d(
            data_list,
            max_points_per_file=args.max_points_per_file,
            umag_min=args.umag_min,
            test_size=args.test_size,
            val_size=args.val_size,
            logger=logger,
        )
    except RuntimeError as exc:
        logger.error(str(exc))
        logger.error("Training aborted — no data to train on.")
        return
    VEL_MAX = splits['VEL_MAX']
    WS_MAX  = splits['WS_MAX']
    X_train, Y_train = splits['train']['X'], splits['train']['Y']
    X_val,   Y_val   = splits['val']['X'],   splits['val']['Y']
    X_test,  Y_test  = splits['test']['X'],  splits['test']['Y']

    # ---- Collocation points: (x, y, z) in [0,1], ws sampled from training ----
    np.random.seed(42)
    x_coll = np.random.uniform(0, 1, (args.cpoints, 1)).astype(np.float32)
    y_coll = np.random.uniform(0, 1, (args.cpoints, 1)).astype(np.float32)
    z_coll = np.random.uniform(0, 1, (args.cpoints, 1)).astype(np.float32)
    # Sample ws from training data's unique wind speeds
    unique_ws_norm = np.unique(X_train[:, 3])
    ws_coll = np.random.choice(unique_ws_norm, size=args.cpoints).reshape(-1, 1).astype(np.float32)

    logger.info(f"Collocation: {args.cpoints} points in (x, y, z, ws)")
    logger.info(f"Physics weight alpha = {args.alpha}")

    # ---- Build model ----
    model = PhysicsMLP3D(hidden=args.hidden, n_layers=args.n_layers)
    _ = model(tf.zeros((1, 4)))  # build
    n_params = sum(p.numpy().size for p in model.trainable_variables)
    logger.info(f"PhysicsMLP3D: {n_params:,} parameters  "
                f"({args.n_layers} blocks x {args.hidden} hidden, tanh, skip connections)")

    # ---- Load pretrained weights ----
    if args.init_weights and os.path.exists(args.init_weights):
        try:
            model.load_weights(args.init_weights)
            logger.info(f"Loaded pretrained weights from: {args.init_weights}")
        except Exception as e:
            logger.warning(f"Failed to load pretrained weights: {e}")

    # ---- Optimizer with CosineDecay LR ----
    n_batches = len(X_train) // args.batch_size + 1
    lr_schedule = tf.keras.optimizers.schedules.CosineDecay(
        args.learning_rate, decay_steps=args.epochs * n_batches)
    opt = tf.keras.optimizers.Adam(learning_rate=lr_schedule)
    loss_fn = tf.keras.losses.MeanSquaredError()

    # ---- tf.data datasets ----
    ds_train = tf.data.Dataset.from_tensor_slices((X_train, Y_train)) \
        .shuffle(len(X_train), seed=42).batch(args.batch_size).prefetch(tf.data.AUTOTUNE)
    ds_val = tf.data.Dataset.from_tensor_slices((X_val, Y_val)).batch(args.batch_size)

    # ---- Collocation tensors ----
    xc = tf.Variable(x_coll, trainable=False)
    yc = tf.Variable(y_coll, trainable=False)
    zc = tf.Variable(z_coll, trainable=False)
    wsc = tf.constant(ws_coll, dtype=tf.float32)

    # ---- Training loop ----
    hist = {'epoch': [], 'train_loss': [], 'val_loss': [],
            'data_loss': [], 'phys_loss': [], 'div_loss': []}
    best_val = float('inf')
    patience_counter = 0
    best_weights = None

    logger.info(f"\nTraining PhysicsMLP3D for up to {args.epochs} epochs ...")

    for ep in range(args.epochs):
        batch_losses = []
        for xb, yb in ds_train:
            with tf.GradientTape() as tape:
                pred = model(xb, training=True)
                data_loss = loss_fn(yb, pred)

                phys_total, l_pde, l_div = compute_physics_loss_3d(
                    model, xc, yc, zc, wsc,
                    Lx, Ly, Lz, args.nu, args.w_div)

                total_loss = (1.0 - args.alpha) * data_loss + args.alpha * phys_total

            grads = tape.gradient(total_loss, model.trainable_variables)
            clipped, _ = tf.clip_by_global_norm(grads, args.clip_value)
            opt.apply_gradients(zip(clipped, model.trainable_variables))
            batch_losses.append(float(total_loss))

        avg_train = np.mean(batch_losses)

        # Validation
        val_losses = []
        for xb, yb in ds_val:
            pred_v = model(xb, training=False)
            val_losses.append(float(loss_fn(yb, pred_v)))
        avg_val = np.mean(val_losses)

        # Log every 10 epochs
        if ep % 10 == 0 or ep == args.epochs - 1:
            hist['epoch'].append(ep)
            hist['train_loss'].append(avg_train)
            hist['val_loss'].append(avg_val)
            hist['data_loss'].append(float(data_loss))
            hist['phys_loss'].append(float(l_pde))
            hist['div_loss'].append(float(l_div))
            logger.info(f"Epoch {ep:>4d}: train={avg_train:.4e}  val={avg_val:.4e}  "
                        f"phys={float(phys_total):.2e}  div={float(l_div):.2e}  "
                        f"best={best_val:.4e}  pat={patience_counter}/{args.patience}")

        # Early stopping on val loss
        if avg_val < best_val:
            best_val = avg_val
            patience_counter = 0
            best_weights = model.get_weights()
        else:
            patience_counter += 1

        if patience_counter >= args.patience:
            logger.info(f"Early stopping at epoch {ep}")
            break

    # Restore best weights
    if best_weights is not None:
        model.set_weights(best_weights)
    epochs_trained = ep + 1

    # ---- Save model ----
    model_path = os.path.join(experiment_dir, f"{args.model_fname}.weights.h5")
    model.save_weights(model_path)

    # Normalization metadata
    norm_meta = {
        "x_min": float(x_min), "x_max": float(x_max),
        "y_min": float(y_min), "y_max": float(y_max),
        "z_min": float(z_min), "z_max": float(z_max),
        "VEL_MAX": VEL_MAX, "WS_MAX": WS_MAX,
        "Lx": float(Lx), "Ly": float(Ly), "Lz": float(Lz),
    }
    norm_path = os.path.join(experiment_dir, f"{args.model_fname}.normalization.json")
    with open(norm_path, "w") as f:
        json.dump(norm_meta, f, indent=2)

    # Run configuration
    run_path = os.path.join(experiment_dir, f"{args.model_fname}.run.json")
    with open(run_path, "w") as f:
        json.dump(vars(args), f, indent=2, default=str)

    # Model metadata
    model_meta = {
        "model_type": "PINN",
        "model_class": "PhysicsMLP3D",
        "input_dim": 4,
        "input_names": ["x_norm", "y_norm", "z_norm", "ws_norm"],
        "n_hidden_layers": args.n_layers,
        "hidden_dim": args.hidden,
        "activation": "tanh",
        "skip_connections": True,
        "output_dim": 2,
        "output_names": ["u_norm", "v_norm"],
        "output_units": "normalised (multiply by VEL_MAX for m/s)",
        "x_min": float(x_min), "x_max": float(x_max),
        "y_min": float(y_min), "y_max": float(y_max),
        "z_min": float(z_min), "z_max": float(z_max),
        "VEL_MAX": VEL_MAX,
        "WS_MAX": WS_MAX,
        "best_val_loss": float(best_val),
        "epochs_trained": epochs_trained,
        "alpha": args.alpha,
        "ws_conditioned": True,
        "z_conditioned": True,
    }
    meta_path = os.path.join(experiment_dir, f"{args.model_fname}.model_meta.json")
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

    rmse_u = np.sqrt(np.mean((u_pred - u_true)**2))
    rmse_v = np.sqrt(np.mean((v_pred - v_true)**2))
    rmse_spd = np.sqrt(np.mean((spd_pred - spd_true)**2))

    logger.info("=== Final Test Results ===")
    logger.info(f"RMSE_u: {rmse_u:.3f} m/s")
    logger.info(f"RMSE_v: {rmse_v:.3f} m/s")
    logger.info(f"RMSE_speed: {rmse_spd:.3f} m/s")
    logger.info(f"Model saved to {model_path}")

    # Save training history
    hist_path = os.path.join(experiment_dir, 'training_history.csv')
    pd.DataFrame(hist).to_csv(hist_path, index=False)
    logger.info(f"Training history saved -> {hist_path}")


if __name__ == "__main__":
    main()