import os, sys
import random, logging
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers
import logging

# -----------------------------
# Domain bounds (meters)
# -----------------------------
x_min, x_max = 0.0, 100.0
# IMPORTANT: north/top is y=0 (y_min); south/bottom is y=y_max
# Keep y_min at 0.0 to reflect this convention

y_min, y_max = 0.0, 200.0

# -----------------------------
# Reproducibility
# -----------------------------
np.random.seed(42)
random.seed(42)
tf.random.set_seed(42)


def speed(u, v):
    return tf.sqrt(tf.square(u) + tf.square(v) + 1e-12)


# --- helper: warmup→hold→decay schedule (returns a float) ---
def piecewise_dir_weight(
    epoch, warm_start, warm_end, decay_start, decay_end, final_ratio
):
    # 0→1 between warm_start..warm_end
    if epoch < warm_start:
        w = 0.0
    elif epoch < warm_end:
        w = (epoch - warm_start) / max(1, (warm_end - warm_start))
    # hold at 1.0
    elif epoch < decay_start:
        w = 1.0
    # 1.0→final_ratio between decay_start..decay_end
    elif epoch < decay_end:
        r = (epoch - decay_start) / max(1, (decay_end - decay_start))
        w = (1.0 - r) + final_ratio * r
    else:
        w = final_ratio
    return float(np.clip(w, 0.0, 1.0))


def mag_penalty(u, v, w, coef=1e-4):
    sp2 = tf.square(u) + tf.square(v)
    return coef * tf.reduce_sum(w * sp2) / (tf.reduce_sum(w) + 1e-12)


def soft_gate(x, thresh=0.3, k=8.0):
    # Smooth step from 0→1 around thresh; k controls sharpness
    # gate(x>thresh)
    return 1.0 / (1.0 + np.exp(-k * (x - thresh)))


# def inflow_gates_from_uv(u, v, thresh=0.3, k=8.0):
#     """
#     u>0 eastward, v>0 southward (your convention). Inflow if velocity points into the domain:
#       - North edge inflow when v > +thresh (flow from north blowing southward into domain)
#       - South edge inflow when v < -thresh
#       - West  edge inflow when u > +thresh
#       - East  edge inflow when u < -thresh
#     Returns 4 arrays (N_times, 1) with gate values in [0,1].
#     """
#     u = np.asarray(u).reshape(-1, 1)
#     v = np.asarray(v).reshape(-1, 1)
#     gN = soft_gate(v, thresh, k)  # v > +thresh
#     gS = soft_gate(-v, thresh, k)  # v < -thresh
#     gW = soft_gate(u, thresh, k)  # u > +thresh
#     gE = soft_gate(-u, thresh, k)  # u < -thresh
#     # Note: Using print here to avoid logger dependency in utility function
#     logger.info(
#         f"[gate diag] mean gates: N={float(gN.mean()):.2f} S={float(gS.mean()):.2f} "
#         f"W={float(gW.mean()):.2f} E={float(gE.mean()):.2f} thr={thresh}"
#     )
#     return gN, gS, gW, gE


def cosine_dir_loss(u_pred, v_pred, u_true, v_true, w, speed_min=0.25):
    # speeds
    sp_p = tf.sqrt(tf.square(u_pred) + tf.square(v_pred) + 1e-12)
    sp_t = tf.sqrt(tf.square(u_true) + tf.square(v_true) + 1e-12)

    # unit vectors
    upx, upy = u_pred / sp_p, v_pred / sp_p
    utx, uty = u_true / sp_t, v_true / sp_t

    # cosine similarity and 1 - cos(angle)
    cos_sim = upx * utx + upy * uty
    ang_loss = 1.0 - tf.clip_by_value(cos_sim, -1.0, 1.0)

    # mask out calms by true speed
    mask = tf.cast(sp_t >= speed_min, tf.float32)
    w_eff = w * mask
    return tf.reduce_sum(w_eff * ang_loss) / (tf.reduce_sum(w_eff) + 1e-12)


def mae_dir_weighted(u1, v1, u2, v2):
    v1n, v2n = -v1, -v2
    a = (270.0 - np.degrees(np.arctan2(v1n, u1))) % 360.0
    b = (270.0 - np.degrees(np.arctan2(v2n, u2))) % 360.0
    d = (a - b + 180.0) % 360.0 - 180.0
    w = np.sqrt(u2**2 + v2**2)  # weight by truth speed
    return float(np.sum(np.abs(d) * w) / (np.sum(w) + 1e-12))


# --- true weighted MSE ---
def weighted_mse(y_pred, y_true, w):
    return tf.reduce_sum(w * tf.square(y_pred - y_true)) / (tf.reduce_sum(w) + 1e-12)


def calm_weight(speed_mag, s0=0.5, gamma=2.0, floor=0.005):
    """
    Down-weight calm winds smoothly.
    speed_mag: 1-D array of |(u,v)| in m/s
    s0: soft knee (m/s). Larger => more down-weighting of small speeds
    gamma: sharpness. Larger => steeper drop near zero
    floor: minimum weight so points aren't completely ignored
    """
    w = (speed_mag / (speed_mag + s0 + 1e-12)) ** gamma
    return np.maximum(w, floor)


def normalize(val, min_val, max_val):
    return (val - min_val) / (max_val - min_val + 1e-12)


class PINN(tf.keras.Model):
    """Feedforward network that outputs PHYSICAL u,v (m/s)."""

    def __init__(self, output_dim=2):
        super().__init__()
        self.hidden = []
        for _ in range(6):
            self.hidden.append(layers.Dense(128))
            self.hidden.append(layers.Activation("swish"))
        self.out = layers.Dense(output_dim)  # linear -> physical u,v

    def call(self, inputs):
        x = inputs
        for layer in self.hidden:
            x = layer(x)
        return self.out(x)


class PhysicsMLP3D(tf.keras.Model):
    """
    (x, y, z, ws) -> (u_norm, v_norm)
    4-input model with tanh activation and skip (residual) connections.
    Ported from explore_pinn.ipynb where it trained successfully.
    """

    def __init__(self, hidden=128, n_layers=4):
        super().__init__()
        self.input_proj = layers.Dense(hidden, activation="tanh")
        self.blocks = []
        for _ in range(n_layers):
            self.blocks.append(layers.Dense(hidden, activation="tanh"))
        self.out_layer = layers.Dense(2)  # (u_norm, v_norm)

    def call(self, inputs, training=False):
        x = self.input_proj(inputs)
        for block in self.blocks:
            x = x + block(x)  # skip/residual connection
        return self.out_layer(x)


def pinn_loss(
    model,
    # Collocation (normalized to [0,1])
    x_c,
    y_c,
    t_c,
    # Boundary (normalized to [0,1] for coords/time; PHYSICAL targets u_b,v_b)
    x_b,
    y_b,
    t_b,
    u_b,
    v_b,
    weights_b,
    # Geometry/time scales (physical extents)
    Lx,
    Ly,
    Lt,
    nu,
    alpha=0.3,
    w_div=1.0,
    additional_data=None,
    center_lambda=1.0,
    w_dir_boundary=0.0,
    w_dir_center=0.0,
    dir_loss_speed_min=0.25,
    w_speed_boundary=0.0,
    w_speed_center=0.0,
):
    """
    Chain-rule-correct PINN loss for 2D viscous Burgers-like flow (no pressure).
    - Inputs (x_c,y_c,t_c,x_b,y_b,t_b) are normalized to [0,1].
    - Targets u_b,v_b are in physical units (m/s).
    - Network outputs physical u,v.
    - additional_data: optional list of (x,y,t,u,v,weight) interior measurements.
    """
    invLx = 1.0 / Lx
    invLy = 1.0 / Ly
    invLt = 1.0 / Lt

    with tf.GradientTape(persistent=True) as tape2:
        tape2.watch([x_c, y_c, t_c])
        with tf.GradientTape(persistent=True) as tape1:
            tape1.watch([x_c, y_c, t_c])
            inputs_c = tf.concat([x_c, y_c, t_c], axis=1)
            uv_c = model(inputs_c)  # physical
            Uc = uv_c[:, 0:1]
            Vc = uv_c[:, 1:2]

        # gradients wrt normalized inputs
        U_xn = tape1.gradient(Uc, x_c)
        U_yn = tape1.gradient(Uc, y_c)
        U_tn = tape1.gradient(Uc, t_c)
        V_xn = tape1.gradient(Vc, x_c)
        V_yn = tape1.gradient(Vc, y_c)
        V_tn = tape1.gradient(Vc, t_c)

    # second derivatives wrt normalized inputs
    U_xxn = tape2.gradient(U_xn, x_c)
    U_yyn = tape2.gradient(U_yn, y_c)
    V_xxn = tape2.gradient(V_xn, x_c)
    V_yyn = tape2.gradient(V_yn, y_c)

    # chain rule to physical derivatives
    Ux = U_xn * invLx
    Uy = U_yn * invLy
    Ut = U_tn * invLt
    Vx = V_xn * invLx
    Vy = V_yn * invLy
    Vt = V_tn * invLt

    Uxx = U_xxn * (invLx**2)
    Uyy = U_yyn * (invLy**2)
    Vxx = V_xxn * (invLx**2)
    Vyy = V_yyn * (invLy**2)

    # PDE residuals (2D viscous Burgers-like; add pressure for full NS)
    f_u = Ut + (Uc * Ux + Vc * Uy) - nu * (Uxx + Uyy)
    f_v = Vt + (Uc * Vx + Vc * Vy) - nu * (Vxx + Vyy)

    # approximate incompressibility
    div = Ux + Vy

    physics_loss = (
        tf.reduce_mean(tf.square(f_u))
        + tf.reduce_mean(tf.square(f_v))
        + w_div * tf.reduce_mean(tf.square(div))
    )

    # boundary/data loss (physical units) — boundary term
    inputs_b = tf.concat([x_b, y_b, t_b], axis=1)
    uv_b_pred = model(inputs_b)
    Ub = uv_b_pred[:, 0:1]
    Vb = uv_b_pred[:, 1:2]

    # Boundary term
    l_b = weighted_mse(Ub, u_b, weights_b) + weighted_mse(Vb, v_b, weights_b)

    l_b_dir = cosine_dir_loss(Ub, Vb, u_b, v_b, weights_b, speed_min=dir_loss_speed_min)

    # Center term(s)
    l_b_mag = mag_penalty(Ub, Vb, weights_b, coef=1e-4)
    l_c_mag = tf.constant(0.0, tf.float32)
    l_c = tf.constant(0.0, tf.float32)
    l_c_dir = tf.constant(0.0, tf.float32)
    l_b_spd = weighted_mse(speed(Ub, Vb), speed(u_b, v_b), weights_b)
    l_c_spd = tf.constant(0.0, tf.float32)
    if additional_data:
        for xd, yd, td, ud, vd, wd in additional_data:
            inputs_d = tf.concat([xd, yd, td], axis=1)
            uv_d = model(inputs_d)
            Ud, Vd = uv_d[:, 0:1], uv_d[:, 1:2]
            l_c += weighted_mse(Ud, ud, wd) + weighted_mse(Vd, vd, wd)
            l_c_mag += mag_penalty(Ud, Vd, wd, coef=1e-4)  # Keep coef tiny (1e-4…5e-4)
            l_c_dir += cosine_dir_loss(Ud, Vd, ud, vd, wd, speed_min=dir_loss_speed_min)
            l_c_spd += weighted_mse(speed(Ud, Vd), speed(ud, vd), wd)

    data_loss = (
        (l_b + center_lambda * l_c)
        + (w_dir_boundary * l_b_dir)
        + (center_lambda * w_dir_center * l_c_dir)
        + (w_speed_boundary * l_b_spd)
        + (center_lambda * w_speed_center * l_c_spd)
        + (l_b_mag + center_lambda * l_c_mag)
    )
    total = alpha * physics_loss + (1.0 - alpha) * data_loss
    del tape1, tape2
    return (
        total,
        physics_loss,
        data_loss,
        {
            "fu": f_u,
            "fv": f_v,
            "div": div,
            "l_b": l_b,
            "l_c": l_c,
            "l_b_dir": l_b_dir,
            "l_c_dir": l_c_dir,
        },
    )


@tf.function(jit_compile=False)  # set to False if your TF build lacks XLA or errors
def train_step(
    model,
    opt,
    x_c,
    y_c,
    t_c,
    x_b,
    y_b,
    t_b,
    u_b,
    v_b,
    w_b,
    Lx,
    Ly,
    Lt,
    nu,
    alpha,
    w_div,
    add_data,
    center_lambda,
    w_dir_boundary,
    w_dir_center,
    dir_loss_speed_min,
    w_speed_boundary,
    w_speed_center,
):
    with tf.GradientTape() as tape:
        loss, ploss, dloss, aux = pinn_loss(
            model,
            x_c,
            y_c,
            t_c,
            x_b,
            y_b,
            t_b,
            u_b,
            v_b,
            w_b,
            Lx,
            Ly,
            Lt,
            nu,
            alpha=alpha,
            w_div=w_div,
            additional_data=add_data,
            center_lambda=center_lambda,
            w_dir_boundary=w_dir_boundary,
            w_dir_center=w_dir_center,
            dir_loss_speed_min=dir_loss_speed_min,
            w_speed_boundary=w_speed_boundary,
            w_speed_center=w_speed_center,
        )
    grads = tape.gradient(loss, model.trainable_variables)
    opt.apply_gradients(zip(grads, model.trainable_variables))
    return loss, ploss, dloss, aux


def log_residual_norms(aux_dict, logger=None):
    fu_rms = tf.sqrt(tf.reduce_mean(tf.square(aux_dict["fu"]))).numpy()
    fv_rms = tf.sqrt(tf.reduce_mean(tf.square(aux_dict["fv"]))).numpy()
    div_rms = tf.sqrt(tf.reduce_mean(tf.square(aux_dict["div"]))).numpy()
    message = f"RMS(f_u)={fu_rms:.3e} RMS(f_v)={fv_rms:.3e} RMS(div)={div_rms:.3e}"
    logger.info(message)
    return fu_rms, fv_rms, div_rms
