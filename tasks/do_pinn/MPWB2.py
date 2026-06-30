import os, sys
import random, logging
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers

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


# def _dir_from_uv(u, v):
#     v_north = -v
#     return (270.0 - np.degrees(np.arctan2(v_north, u))) % 360.0


# def _circ_diff_deg(a, b):
#     return (a - b + 180.0) % 360.0 - 180.0


# def _dir_metrics(u_pred, v_pred, u_true, v_true, thr=None):
#     u_pred = np.asarray(u_pred).reshape(-1,1)
#     v_pred = np.asarray(v_pred).reshape(-1,1)
#     u_true = np.asarray(u_true).reshape(-1,1)
#     v_true = np.asarray(v_true).reshape(-1,1)

#     sp_pred = np.sqrt(u_pred**2 + v_pred**2).ravel()
#     sp_true = np.sqrt(u_true**2 + v_true**2).ravel()

#     if thr is None:
#         mask = np.ones_like(sp_true, dtype=bool)
#     else:
#         mask = (sp_true > thr) & (sp_pred > thr)

#     if mask.sum() == 0:
#         return {"MAE_dir": np.nan, "WMAE_dir": np.nan, "n": 0}

#     d_pred = _dir_from_uv(u_pred[mask], v_pred[mask]).ravel()
#     d_true = _dir_from_uv(u_true[mask], v_true[mask]).ravel()
#     ang   = np.abs(_circ_diff_deg(d_pred, d_true))

#     w = sp_true[mask].ravel()
#     w = w / (w.sum() + 1e-12)

#     return {
#         "MAE_dir":  float(np.mean(ang)),
#         "WMAE_dir": float(np.sum(w * ang)),
#         "n":        int(mask.sum())
#     }


def soft_gate(x, thresh=0.3, k=8.0):
    # Smooth step from 0→1 around thresh; k controls sharpness
    # gate(x>thresh)
    return 1.0 / (1.0 + np.exp(-k * (x - thresh)))


def inflow_gates_from_uv(u, v, thresh=0.3, k=8.0):
    """
    u>0 eastward, v>0 southward (your convention). Inflow if velocity points into the domain:
      - North edge inflow when v > +thresh (flow from north blowing southward into domain)
      - South edge inflow when v < -thresh
      - West  edge inflow when u > +thresh
      - East  edge inflow when u < -thresh
    Returns 4 arrays (N_times, 1) with gate values in [0,1].
    """
    u = np.asarray(u).reshape(-1, 1)
    v = np.asarray(v).reshape(-1, 1)
    gN = soft_gate(v, thresh, k)  # v > +thresh
    gS = soft_gate(-v, thresh, k)  # v < -thresh
    gW = soft_gate(u, thresh, k)  # u > +thresh
    gE = soft_gate(-u, thresh, k)  # u < -thresh
    # Note: Using print here to avoid logger dependency in utility function
    print(
        f"[gate diag] mean gates: N={float(gN.mean()):.2f} S={float(gS.mean()):.2f} "
        f"W={float(gW.mean()):.2f} E={float(gE.mean()):.2f} thr={thresh}"
    )
    return gN, gS, gW, gE


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


def setup_logger(experiment_dir):
    """Set up logger to write to both console and file in experiment directory"""
    try:
        # Create logger
        logger = logging.getLogger("PINN_Experiment")
        logger.setLevel(logging.INFO)

        # Clear any existing handlers
        logger.handlers.clear()

        # Create formatters
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

        # File handler - save to experiment directory
        log_file = os.path.join(experiment_dir, "experiment.log")
        file_handler = logging.FileHandler(log_file, mode="w")  # 'w' to start fresh
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

        # Console handler - continue showing on console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(message)s"
        )  # Simpler format for console
        console_handler.setFormatter(console_formatter)

        # Add handlers to logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        # Test the logger
        logger.info("Logger successfully initialized")

        return logger
    except Exception as e:
        print(f"Warning: Could not set up logger: {e}")
        print("Falling back to print statements")
        return None


def log_message(logger, message, level="info"):
    """Helper function to log message with fallback to print"""
    if logger:
        if level == "info":
            logger.info(message)
        elif level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)
    else:
        if level == "error":
            print(f"ERROR: {message}")
        elif level == "warning":
            print(f"WARNING: {message}")
        else:
            print(message)


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
    message = f"   RMS(f_u)={fu_rms:.3e} RMS(f_v)={fv_rms:.3e} RMS(div)={div_rms:.3e}"
    if logger:
        logger.info(message)
    else:
        print(message)
    return fu_rms, fv_rms, div_rms


# def main():
#     parser = argparse.ArgumentParser(description='PINN for 2D wind speed modeling')
#     parser.add_argument('input', help='EDGE sensor file: timestamp, speed(mph), direction(deg from North CW)')
#     parser.add_argument('center_input', type=str,
#                         help='CENTER sensor file: timestamp, speed(mph), direction(deg from North CW)')
#     parser.add_argument('model_fname', help='Model save name')
#     parser.add_argument('--epochs', '-e', type=int, default=5000)
#     parser.add_argument('--cpoints', '-c', type=int, default=5000)
#     # Input sensor location (prefer meters; fallback to fractions)
#     # From paper: https://www.mdpi.com/1424-8220/24/19/6200
#     #      daviscupsin sensor is 46m from north boundary
#     #      in the middle along east-west (x) axis (50, given x-max is 100)
#     parser.add_argument('--sensor_x', type=float, default=None,
#                     help='Input sensor x (meters). x=0 is west.')
#     parser.add_argument('--sensor_y', type=float, default=None,
#                     help='Input sensor y (meters). y=0 is north.')

#     parser.add_argument('--sensor_x_frac', type=float, default=0.5,
#                     help='Alternative: x as fraction [0,1] of width (ignored if --sensor_x given).')
#     parser.add_argument('--sensor_y_frac', type=float, default=0.23, #was 0.5 b4 fix
#                     help='Alternative: y as fraction [0,1] of height (ignored if --sensor_y given).')

#     parser.add_argument('--N_edge', type=int, default=50, help='Number of points along each boundary edge')
#     parser.add_argument('--nu', type=float, default=0.01, help='Viscosity-like term in PDE units')
#     parser.add_argument('--alpha', type=float, default=0.3, help='Weight on physics vs data')
#     parser.add_argument('--w_div', type=float, default=1.0, help='Weight on divergence penalty')
#     parser.add_argument('--outscale', type=float, default=0.42819, help='Multiplied by the boundary data (daviscupsout) to get the inside boundary values')
#     parser.add_argument('--calm_s0', type=float, default=0.5, help='Soft knee (m/s) for calm weighting')
#     parser.add_argument('--calm_gamma', type=float, default=2.0, help='Sharpness for calm weighting')
#     parser.add_argument('--min_weight', type=float, default=0.005, help='Minimum data-loss weight')
#     #add different options for the inside sensor/input data
#     parser.add_argument('--center_calm_s0', type=float, default=0.3)
#     parser.add_argument('--center_calm_gamma', type=float, default=1.0)
#     parser.add_argument('--center_min_weight', type=float, default=0.02)
#     parser.add_argument('--center_loss_weight', type=float, default=1.0,
#                     help='Multiplier for CENTER data term in the loss')
#     parser.add_argument('--dir_mask_speed', type=float, default=0.2,
#                     help='If set, compute direction metrics only where both true & pred speeds exceed this (m/s).')
#     parser.add_argument('--northonly', action='store_true', help='Use the boundary data across the north boundary only')
#     #changes to help manage predictions of wind direction - touchy b/c it is scale-free (angles wrap) w/ loss=scale-aware
#     parser.add_argument('--target_cb_ratio', type=float, default=0.8,
#         help='Target ratio (center/boundary) for effective data weight at epoch 0.')
#     parser.add_argument('--resample_c_every', type=int, default=50,
#         help='Resample collocation points every N epochs (0=never).')
#     parser.add_argument('--alpha_start', type=float, default=None,
#         help='If set, linearly ramp alpha from this to --alpha by --alpha_ramp_epochs.')
#     parser.add_argument('--alpha_ramp_epochs', type=int, default=1500)

#     # Split the direction loss into center vs boundary weights
#     parser.add_argument('--w_dir_center', type=float, default=1.2,
#         help='Direction loss weight for center interior data')
#     parser.add_argument('--w_dir_boundary', type=float, default=0.4,
#         help='Direction loss weight for boundary data')
#     parser.add_argument('--dir_loss_speed_min', type=float, default=0.2,
#         help='Apply direction loss only where true speed >= this (m/s)')
#     parser.add_argument('--center_lambda_ramp_epochs', type=int, default=3200)
#     parser.add_argument('--isamp_power', type=float, default=2.5)
#     parser.add_argument('--isamp_tail',  type=float, default=0.05)
#     parser.add_argument('--w_speed_center', type=float, default=0.0)
#     parser.add_argument('--w_speed_boundary', type=float, default=0.0)
#     parser.add_argument('--init_weights', type=str, default=None)

#     args = parser.parse_args()

#     # -----------------------------
#     # Create experiment folder and setup logging
#     # -----------------------------
#     timestamp = datetime.now().strftime("experiment_%m-%d-%H-%M-%S")
#     experiment_dir = os.path.join(os.getcwd(), timestamp)
#     os.makedirs(experiment_dir, exist_ok=True)

#     # Setup logger for this experiment
#     logger = setup_logger(experiment_dir)
#     if logger:
#         logger.info(f"Created experiment directory: {experiment_dir}")
#         logger.info(f"Logging to: {os.path.join(experiment_dir, 'experiment.log')}")
#     else:
#         print(f"Created experiment directory: {experiment_dir}")
#         print("Warning: Logging to file disabled, using console only")

#     if not os.path.isfile(args.input):
#         log_message(logger, f'File not found: {args.input}', 'error')
#         sys.exit(1)
#     if args.center_input is not None and not os.path.isfile(args.center_input):
#         log_message(logger, f'Center file not found: {args.center_input}', 'error')
#         sys.exit(1)

#     # -----------------------------
#     # Load & preprocess data (EDGE and optional CENTER)
#     # -----------------------------
#     data_edge = np.loadtxt(args.input)
#     data_edge = data_edge[np.isfinite(data_edge).all(axis=1)]  #in case of NaNs
#     data_edge   = data_edge[np.argsort(data_edge[:, 0])]
#     ts_edge     = data_edge[:, 0]
#     spd_edge_mph, dir_edge_deg = data_edge[:, 1], data_edge[:, 2]

#     # EDGE sensor preprocessing:
#     speeds_edge = spd_edge_mph * 0.44704  # mph → m/s
#     speeds_edge *= args.outscale
#     # No need for eps filter now — all speeds kept, but calm speeds get small weights
#     w_ts_edge = calm_weight(
#         speeds_edge,
#         s0=args.calm_s0, gamma=args.calm_gamma, floor=args.min_weight
#     ).reshape(-1, 1)
#     logger.info(f"EDGE Weights: min={w_ts_edge.min():.3f}, max={w_ts_edge.max():.3f}, "
#                 f"median={np.median(w_ts_edge):.3f}, p10={np.percentile(w_ts_edge,10):.3f}, "
#                 f"p90={np.percentile(w_ts_edge,90):.3f}")

#     theta_edge = np.deg2rad(dir_edge_deg)
#     u_edge_all = (-speeds_edge * np.sin(theta_edge)).reshape(-1, 1)  # east-positive
#     v_edge_all = (+speeds_edge * np.cos(theta_edge)).reshape(-1, 1)  # south-positive

#     # Load and convert CENTER sensor to components, then align via interpolation
#     data_center = np.loadtxt(args.center_input)
#     data_center = data_center[np.isfinite(data_center).all(axis=1)] #in case of NaNs
#     data_center = data_center[np.argsort(data_center[:, 0])]
#     ts_center   = data_center[:, 0]
#     spd_center_mph, dir_center_deg = data_center[:, 1], data_center[:, 2]

#     # CENTER sensor preprocessing
#     speeds_center = spd_center_mph * 0.44704
#     w_ts_center = calm_weight(
#         speeds_center,
#         s0=args.center_calm_s0, gamma=args.center_calm_gamma, floor=args.center_min_weight
#     ).reshape(-1, 1)
#     pct_floor_raw = 100.0 * np.mean((w_ts_center <= args.center_min_weight + 1e-12))
#     logger.info(f"CENTER weights at floor (raw): {pct_floor_raw:.1f}%")
#     logger.info(f"CENTER Weights: min={w_ts_center.min():.3f}, max={w_ts_center.max():.3f}, "
#                 f"median={np.median(w_ts_center):.3f}, p10={np.percentile(w_ts_center,10):.3f}, "
#                 f"p90={np.percentile(w_ts_center,90):.3f}")

#     theta_center = np.deg2rad(dir_center_deg)
#     u_center_all = (-speeds_center * np.sin(theta_center)).reshape(-1, 1)
#     v_center_all = (+speeds_center * np.cos(theta_center)).reshape(-1, 1)

#     # Interpolation
#     mask = (ts_edge >= ts_center.min()) & (ts_edge <= ts_center.max())
#     if not np.any(mask):
#         raise ValueError("No overlapping timestamps between edge and center sensors.")

#     ts_aligned = ts_edge[mask]
#     u_edge = u_edge_all[mask]
#     v_edge = v_edge_all[mask]

#     u_center = np.interp(ts_aligned, ts_center, u_center_all[:, 0]).reshape(-1, 1)
#     v_center = np.interp(ts_aligned, ts_center, v_center_all[:, 0]).reshape(-1, 1)
#     logger.info(f"Aligned samples: {len(ts_aligned)}/{len(ts_edge)} "
#                 f"({100*len(ts_aligned)/len(ts_edge):.1f}%)")
#     cent_speeds = np.sqrt(u_center[:,0]**2 + v_center[:,0]**2)
#     p = np.percentile(cent_speeds, [10, 25, 50, 75, 90])
#     logger.info(f"CENTER speed percentiles (m/s): {p}")

#     # Sanity checks
#     assert u_edge.shape == v_edge.shape == (len(ts_aligned), 1)
#     assert u_center.shape == v_center.shape == (len(ts_aligned), 1)

#     # Global time normalization based on aligned timestamps
#     t_min, t_max = ts_aligned.min(), ts_aligned.max()
#     t_norm = ((ts_aligned - t_min) / (t_max - t_min + 1e-12)).reshape(-1, 1)

#     # -----------------------------
#     # Boundary geometry (edges) with north at y=0 (y_min)
#     # -----------------------------
#     N_edge = args.N_edge
#     x_north = np.linspace(x_min, x_max, N_edge)
#     y_north = np.full_like(x_north, y_min)  # y=0 top

#     x_south = np.linspace(x_min, x_max, N_edge)
#     y_south = np.full_like(x_south, y_max)

#     y_west = np.linspace(y_min, y_max, N_edge)
#     x_west = np.full_like(y_west, x_min)

#     y_east = np.linspace(y_min, y_max, N_edge)
#     x_east = np.full_like(y_east, x_max)

#     x_b_edge = np.concatenate([x_north, x_south, x_west, x_east]).reshape(-1, 1)
#     y_b_edge = np.concatenate([y_north, y_south, y_west, y_east]).reshape(-1, 1)

#     #INSTEAD of all 4 walls, use north only overwriting x_b_edge and y_b_edge FIX THIS with an argument
#     if args.northonly:
#         x_b_edge = x_north.reshape(-1, 1)
#         y_b_edge = y_north.reshape(-1, 1)
#     N_boundary_points = x_b_edge.shape[0]

#     # -----------------------------
#     # Sample timestamps and repeat along boundary points
#     # -----------------------------
#     N_b_time = min(1500, len(t_norm))
#     # Instead of sampling times uniformly (wasting time on calm periods): importance sample times by speed (center or boundary)
#     # importance sample by center speed
#     # Blend a small uniform tail into your speed-weighted probabilities
#     # --- Importance sampling with a uniform tail ---
#     N = len(t_norm)
#     speed = np.hypot(u_center[:, 0], v_center[:, 0]).astype(float)
#     speed = np.nan_to_num(speed, nan=0.0, posinf=0.0, neginf=0.0)

#     # Tune p_power (how aggressively you favor windy periods) and tail (how much exploration you keep). A good starting pair is p_power=2.0, tail=0.10
#     p_power = args.isamp_power     # stronger bias toward windy times (try 1.0–3.0)
#     tail    = args.isamp_tail     # 5% uniform mass; guarantees full support
#     # tail > 0 guarantees every index has positive probability, so replace=False below is always valid even if many speeds are near zero.

#     base = speed ** p_power
#     if base.sum() <= 0 or not np.isfinite(base).all():
#         # all calm / invalid → pure uniform
#         base = np.ones(N, dtype=float) / N
#     else:
#         base = base / base.sum()

#     uniform = np.ones(N, dtype=float) / N
#     probs = (1.0 - tail) * base + tail * uniform

#     # exact normalization guard
#     probs = probs / probs.sum()
#     probs[-1] += (1.0 - probs.sum())
#     logger.info(f"[isamp] p_min={probs.min():.2e} p_max={probs.max():.2e} "
#                 f"H={-np.sum(probs*np.log(probs+1e-12)):.3f} (max {np.log(len(probs)):.3f})")

#     # sample without replacement
#     idx_sample = np.random.choice(N, N_b_time, replace=False, p=probs)


#     # Sanity check
#     assert N_b_time == len(idx_sample) and np.unique(idx_sample).size == N_b_time

#     # EDGE sampled
#     t_edge_sampled = t_norm[idx_sample]           # (N_b_time,1)
#     u_edge_sampled = u_edge[idx_sample]
#     v_edge_sampled = v_edge[idx_sample]
#     w_edge = w_ts_edge[mask]                     # align weights to masked series
#     w_edge_sampled = w_edge[idx_sample]

#     ##########  Soft Gates for windward/leeward boundaries ##############
#     # Build soft inflow gates per sampled time
#     gN, gS, gW, gE = inflow_gates_from_uv(u_edge_sampled, v_edge_sampled,
#                                       thresh=0.30, k=8.0)

#     # Assemble one gate vector per time in the concatenation order: [north, south, west, east]
#     gates_time = []
#     for i in range(N_b_time):
#         if args.northonly:
#             # If training with north-only, just use the north gate
#             g_vec = np.ones((x_b_edge.shape[0], 1), dtype=float)  # all points are north in this mode
#             g_vec[:] = gN[i]
#         else:
#             g_vec = np.concatenate([
#                 np.full((len(x_north), 1), gN[i]),
#                 np.full((len(x_south), 1), gS[i]),
#                 np.full((len(y_west),  1), gW[i]),
#                 np.full((len(y_east),  1), gE[i]),
#             ], axis=0)
#         gates_time.append(g_vec)

#     G = np.vstack(gates_time)  # shape (B*N_b_time, 1)
#     G = np.clip(G, 1e-3, 1.0)   # optional: keep a small floor for numerical stability
#     eps = 0.05  # 10% of boundary weights remain everywhere -- can go to 0.5 if there are overconfident leeward splits later in the training
#     G_eps = eps + (1.0 - eps) * G

#     # Repeat along boundary
#     u_b = np.repeat(u_edge_sampled, N_boundary_points, axis=0)
#     v_b = np.repeat(v_edge_sampled, N_boundary_points, axis=0)
#     t_b_full = np.repeat(t_edge_sampled, N_boundary_points, axis=0)
#     w_full = np.repeat(w_edge_sampled, N_boundary_points, axis=0)

#     # Apply gates to boundary weights (NOT to velocities!)
#    # w_full = w_full * G         # apply gates to boundary weights
#                                 # down-weights leeward edges smoothly
#     w_full = w_full * G_eps #Blend in a small uniform floor so they don't go to zero

#     # Repeat boundary coords for each sampled time so shapes match t_b_full
#     x_b_rep = np.tile(x_b_edge, (N_b_time, 1))  # (B*N_b_time, 1)
#     y_b_rep = np.tile(y_b_edge, (N_b_time, 1))  # (B*N_b_time, 1)

#     # Normalize boundary coords/time only
#     x_b_tf = tf.convert_to_tensor(normalize(x_b_rep, x_min, x_max), dtype=tf.float32)
#     y_b_tf = tf.convert_to_tensor(normalize(y_b_rep, y_min, y_max), dtype=tf.float32)
#     t_b_tf = tf.convert_to_tensor(t_b_full, dtype=tf.float32)

#     # Targets in physical units
#     u_b_tf = tf.convert_to_tensor(u_b, dtype=tf.float32)
#     v_b_tf = tf.convert_to_tensor(v_b, dtype=tf.float32)
#     weights_b_tf = tf.convert_to_tensor(w_full, dtype=tf.float32)

#     # Sanity check
#     assert x_b_tf.shape == y_b_tf.shape == t_b_tf.shape == u_b_tf.shape == v_b_tf.shape == weights_b_tf.shape, f"Boundary shapes mismatch: {x_b_tf.shape}, {y_b_tf.shape}, {t_b_tf.shape}, {u_b_tf.shape}, {v_b_tf.shape}, {weights_b_tf.shape}"

#     # Input sensor (daviscupsin) placed at correct location in the cups at (x,y)
#     # Prefer meters; if not provided, fall back to fractions.
#     if args.sensor_x is not None:
#         x_sensor_m = float(args.sensor_x)
#     else:
#         x_sensor_m = x_min + float(args.sensor_x_frac) * (x_max - x_min)

#     if args.sensor_y is not None:
#         y_sensor_m = float(args.sensor_y)
#     else:
#         y_sensor_m = y_min + float(args.sensor_y_frac) * (y_max - y_min)

#     # Bounds check
#     if not (x_min <= x_sensor_m <= x_max) or not (y_min <= y_sensor_m <= y_max):
#         raise ValueError(
#             f"Sensor location out of bounds: (x={x_sensor_m:.3f}, y={y_sensor_m:.3f}) "
#             f"must satisfy x∈[{x_min},{x_max}], y∈[{y_min},{y_max}]. "
#             "Remember: y=0 is NORTH, x=0 is WEST."
#         )

#     logger.info(f"Placing input sensor at (x={x_sensor_m:.3f} m, y={y_sensor_m:.3f} m) "
#                 f"[norm=({normalize(x_sensor_m, x_min, x_max):.3f}, {normalize(y_sensor_m, y_min, y_max):.3f})]")

#     x_sensor_tf = tf.convert_to_tensor(
#         np.full((N_b_time, 1), normalize(x_sensor_m, x_min, x_max)), dtype=tf.float32
#     )
#     y_sensor_tf = tf.convert_to_tensor(
#         np.full((N_b_time, 1), normalize(y_sensor_m, y_min, y_max)), dtype=tf.float32
#     )
#     t_sensor_tf = tf.convert_to_tensor(t_norm[idx_sample], dtype=tf.float32)

#     u_sensor_tf = tf.convert_to_tensor(u_center[idx_sample], dtype=tf.float32)
#     v_sensor_tf = tf.convert_to_tensor(v_center[idx_sample], dtype=tf.float32)

#     # CENTER weights aligned to ts_aligned (use new, gentler params)
#     speeds_center_aligned = np.sqrt(u_center[:,0]**2 + v_center[:,0]**2)
#     w_center_aligned = calm_weight(
#         speeds_center_aligned,
#         s0=args.center_calm_s0, gamma=args.center_calm_gamma, floor=args.center_min_weight
#     ).reshape(-1, 1)
#     # % of CENTER weights stuck at the floor (aligned to ts_aligned)
#     pct_floor = 100.0 * np.mean((w_center_aligned <= args.center_min_weight + 1e-12))
#     logger.info(f"CENTER weights at floor (aligned): {pct_floor:.1f}%")

#     eff_boundary = float(np.sum(w_full))                 # gated, repeated weight sum
#     eff_center   = float(np.sum(w_center_aligned[idx_sample]))
#     eff_center  *= float(getattr(args, "center_loss_weight", 1.0))

#     logger.info(f"Effective weight sums (gated): boundary≈{eff_boundary:.1f}  center≈{eff_center:.1f}  "
#                 f"ratio center/boundary≈{eff_center/eff_boundary:.3f}")

#     w_sensor_tf = tf.convert_to_tensor(w_center_aligned[idx_sample], dtype=tf.float32)
#     additional_data = [(x_sensor_tf, y_sensor_tf, t_sensor_tf,
#                     u_sensor_tf, v_sensor_tf, w_sensor_tf)]

#     # -----------------------------
#     # Collocation points (sample physical, feed normalized)
#     # -----------------------------
#     N_col = args.cpoints
#     x_c = np.random.uniform(x_min, x_max, (N_col, 1))
#     y_c = np.random.uniform(y_min, y_max, (N_col, 1))
#     t_c = np.random.uniform(t_min, t_max, (N_col, 1))

#     x_c_tf = tf.convert_to_tensor(normalize(x_c, x_min, x_max), dtype=tf.float32)
#     y_c_tf = tf.convert_to_tensor(normalize(y_c, y_min, y_max), dtype=tf.float32)
#     t_c_tf = tf.convert_to_tensor(normalize(t_c, t_min, t_max), dtype=tf.float32)

#     # Scales
#     Lx = tf.constant(x_max - x_min, tf.float32)
#     Ly = tf.constant(y_max - y_min, tf.float32)
#     Lt = tf.constant(t_max - t_min, tf.float32)
#     Lt = tf.maximum(Lt, tf.constant(1e-12, tf.float32))  # avoid divide-by-zero if a single timestamp slips through
#     nu_tf = tf.constant(args.nu, tf.float32)

#     alpha_tf = tf.constant(args.alpha, tf.float32)
#     w_div_tf = tf.constant(args.w_div, tf.float32)
#     add_data = tuple(additional_data)  # tuple avoids retracing, if we later vary the number of interior points, we should pack as a fixed-structure dict or a single stacked tensor to avoid retracing of @tf.function.

#     # -----------------------------
#     # Model & optimizer
#     # -----------------------------
#     pinn_model = PINN()
#     if args.init_weights:
#         _ = pinn_model(tf.zeros((1,3), dtype=tf.float32))  # build
#         pinn_model.load_weights(args.init_weights)
#         logger.info(f"Loaded weights from {args.init_weights}")
#     #optimizer = tf.keras.optimizers.Adam(learning_rate=1e-4)
#     ## Clip gradients to avoid occasional blow-ups when PDE terms spike
#     ##optimizer = tf.keras.optimizers.Adam(learning_rate=1e-4, clipnorm=1.0)

#     # Change the learning rate to help direction
#     lr_sched = tf.keras.optimizers.schedules.PiecewiseConstantDecay(
#         boundaries=[int(0.5*args.epochs), int(0.8*args.epochs)],
#         values=[3e-4, 1e-4, 5e-5]
#     )
#     optimizer = tf.keras.optimizers.Adam(learning_rate=lr_sched, clipnorm=1.0)

#     # Histories
#     loss_hist, phys_hist, data_hist = [], [], []

#     # Calibrate λ₀ using the actual residuals
#     # Quick forward to get epoch-0 residuals
#     inputs_b0 = tf.concat([x_b_tf, y_b_tf, t_b_tf], axis=1)
#     Ub0, Vb0  = tf.split(pinn_model(inputs_b0), 2, axis=1)
#     l_b0 = weighted_mse(Ub0, u_b_tf, weights_b_tf) + weighted_mse(Vb0, v_b_tf, weights_b_tf)

#     inputs_c0 = tf.concat([x_sensor_tf, y_sensor_tf, t_sensor_tf], axis=1)
#     Uc0, Vc0  = tf.split(pinn_model(inputs_c0), 2, axis=1)
#     l_c0 = weighted_mse(Uc0, u_sensor_tf, w_sensor_tf) + weighted_mse( Vc0, v_sensor_tf, w_sensor_tf)

#     # You’ve defined target as a ratio r = C/B.
#     r = float(args.target_cb_ratio)
#     lam0_value = r * (float(l_b0.numpy()) / (float(l_c0.numpy()) + 1e-12))  # solves (λ c)/(b+λ c) = r/(1+r)

#     # Clamp to something sane to avoid runaway dominance
#     lam0_value = float(np.clip(lam0_value, 0.05, 10.0))
#     lam0 = tf.constant(lam0_value, tf.float32)

#     logger.info(f"[λ₀ calibration] l_b0={float(l_b0.numpy()):.4f}  l_c0={float(l_c0.numpy()):.4f}  "
#                 f"target C/B={r:.3f} → lam0≈{lam0_value:.3f}")

#     # -----------------------------
#     # Training loop
#     # -----------------------------
#     # Decide file paths up front (works whether user passed .weights.h5 or not)
#     base_out = args.model_fname if args.model_fname.endswith('.weights.h5') else f"{args.model_fname}.weights.h5"
#     base_out = os.path.join(experiment_dir, os.path.basename(base_out))
#     best_center_path   = base_out.replace(".weights.h5", ".best_center.weights.h5")
#     best_boundary_path = base_out.replace(".weights.h5", ".best_boundary.weights.h5")
#     best_center_wmae = np.inf
#     best_boundary_wmae = np.inf
#     best_center_epoch = -1
#     best_boundary_epoch = -1
#     # how often to evaluate/save
#     eval_every = 200  # or make this an argparse option
#     for epoch in range(args.epochs):
#         # To correct the direction error (which is mostly a boundary-conditioning issue)
#         # Start lambda off strong to favor the center sensor, then let it decay over
#         #     time to give the boundary and the physics more say
#         frac = min(epoch / args.center_lambda_ramp_epochs, 1.0)
#         center_lambda = lam0 * (1.0 - frac) + tf.constant(1.0, tf.float32) * frac

#         if args.resample_c_every and (epoch % args.resample_c_every == 0):
#             x_c = np.random.uniform(x_min, x_max, (N_col, 1))
#             y_c = np.random.uniform(y_min, y_max, (N_col, 1))
#             t_c = np.random.uniform(t_min, t_max, (N_col, 1))
#             x_c_tf = tf.convert_to_tensor(normalize(x_c, x_min, x_max), dtype=tf.float32)
#             y_c_tf = tf.convert_to_tensor(normalize(y_c, y_min, y_max), dtype=tf.float32)
#             t_c_tf = tf.convert_to_tensor(normalize(t_c, t_min, t_max), dtype=tf.float32)

#         if args.alpha_start is not None:
#             frac_a = min(epoch / max(1, args.alpha_ramp_epochs), 1.0)
#             alpha_now = args.alpha_start * (1.0 - frac_a) + args.alpha * frac_a
#             alpha_epoch_tf = tf.constant(alpha_now, tf.float32)
#         else:
#             alpha_epoch_tf = alpha_tf

#         # your schedule (center earlier than boundary; both decay later)
#         w_center_sched   = piecewise_dir_weight(epoch, warm_start=0,   warm_end=600,
#                                         decay_start=1200, decay_end=2200, final_ratio=0.6)
#         w_boundary_sched = piecewise_dir_weight(epoch, warm_start=400, warm_end=1200,
#                                         decay_start=1400, decay_end=2400, final_ratio=0.6)
#         # couple a bit to physics ramp: as alpha ramps up, shrink dir loss slightly
#         if args.alpha_start is not None:
#             frac_a = min(epoch / max(1, args.alpha_ramp_epochs), 1.0)  # 0→1 over your alpha ramp
#             phys_couple = 1.0 - 0.3 * frac_a   # up to -30% by end of alpha ramp
#         else:
#             phys_couple = 1.0

#         w_dir_center_now   = tf.constant(args.w_dir_center   * w_center_sched   * phys_couple, tf.float32)
#         w_dir_boundary_now = tf.constant(args.w_dir_boundary * w_boundary_sched * phys_couple, tf.float32)
#         w_speed_b_tf = tf.constant(args.w_speed_boundary, tf.float32)
#         w_speed_c_tf = tf.constant(args.w_speed_center,   tf.float32)

#         dir_min_tf = tf.constant(args.dir_loss_speed_min, tf.float32)
#         loss, ploss, dloss, aux = train_step(
#             pinn_model, optimizer,
#             x_c_tf, y_c_tf, t_c_tf,
#             x_b_tf, y_b_tf, t_b_tf,
#             u_b_tf, v_b_tf, weights_b_tf,
#             Lx, Ly, Lt, nu_tf,
#             alpha_epoch_tf, w_div_tf, add_data, center_lambda,
#             w_dir_boundary_now, w_dir_center_now, dir_min_tf,
#             w_speed_b_tf, w_speed_c_tf
#         )

#         loss_hist.append(float(loss.numpy()))
#         phys_hist.append(float(ploss.numpy()))
#         data_hist.append(float(dloss.numpy()))

#         if epoch % eval_every == 0 or epoch == args.epochs - 1:
#             tot = float(loss.numpy())
#             ph  = float(ploss.numpy())
#             da  = float(dloss.numpy())
#             logger.info(f"Epoch {epoch:5d} | Total={tot:.4e} | Phys={ph:.4e} | Data={da:.4e}")
#             tot_calc = float(alpha_epoch_tf.numpy())*ph + (1.0-float(alpha_epoch_tf.numpy()))*da
#             logger.info(f"Total(recomp)={tot_calc:.4e} | diff={tot - tot_calc:+.2e}")

#             log_residual_norms(aux, logger)
#             b = float(aux["l_b"].numpy())
#             c = float(aux["l_c"].numpy())
#             b_dir = float(aux["l_b_dir"].numpy())
#             c_dir = float(aux["l_c_dir"].numpy())
#             lam = float(center_lambda.numpy())
#             #share_center = (lam * c) / (b + lam * c + 1e-12)
#             share_center_mse = (lam*c) / (b + lam*c + 1e-12)
#             wbc = float(w_dir_boundary_now.numpy())
#             wcc = float(w_dir_center_now.numpy())
#             share_center_all = (lam*(c + wcc*c_dir)) / (b + lam*c + wbc*b_dir + lam*wcc*c_dir + 1e-12)

#             logger.info(f"data split (MSE only): center_share≈{share_center_mse:.2%}")
#             logger.info(f"data split (incl. dir): center_share≈{share_center_all:.2%}")
#             logger.info(f"Note that these splits do not account for the tiny magnitude penalty added to boundary and center")
#             logger.info(f"[dir] w_center_now={wcc:.3f}  w_boundary_now={wbc:.3f}")
#             #print(f"data split: boundary={b:.4f}  center={c:.4f}  λ={lam:.2f}  center_share≈{share_center:.2%}")

#             # ---- Boundary-mean quick forward ----
#             inputs_b_eval = tf.concat([x_b_tf, y_b_tf, t_b_tf], axis=1)
#             uv_b_all = pinn_model(inputs_b_eval).numpy()
#             B = N_boundary_points
#             u_b_t = uv_b_all[:,0:1].reshape(-1, B).mean(axis=1, keepdims=True)
#             v_b_t = uv_b_all[:,1:2].reshape(-1, B).mean(axis=1, keepdims=True)

#             # true boundary (already sampled)
#             u_b_true = u_edge_sampled
#             v_b_true = v_edge_sampled

#             # For smoothed inputs, the masked set tends to shrink. For readability while training, evaluate with a softer threshold early -- there are too many non-windy days so ALWAYS mask instead
#             # ---- Boundary-mean quick forward ----
#             thr_eval = args.dir_mask_speed  # ← always use the mask, even early
#             met_b = _dir_metrics(u_b_t, v_b_t, u_b_true, v_b_true, thr=thr_eval)
#             wmae_b = met_b["WMAE_dir"]

#             # ---- Center sensor quick forward ----
#             inputs_c_eval = tf.concat([x_sensor_tf, y_sensor_tf, t_sensor_tf], axis=1)
#             uv_c = pinn_model(inputs_c_eval).numpy()
#             u_c_t = uv_c[:,0:1]
#             v_c_t = uv_c[:,1:2]

#             u_c_true = u_sensor_tf.numpy()
#             v_c_true = v_sensor_tf.numpy()

#             sp_c = np.sqrt(u_c_true**2 + v_c_true**2).ravel()
#             frac_above = float((sp_c > args.dir_mask_speed).mean())
#             logger.info(f"[debug] center samples above {args.dir_mask_speed:.2f} m/s: {100*frac_above:.1f}%")

#             # ---- Center sensor quick forward ----
#             met_c = _dir_metrics(u_c_t, v_c_t, u_c_true, v_c_true, thr=thr_eval)
#             wmae_c = met_c["WMAE_dir"]

#             # ---- Save best-by WMAE_dir (center & boundary) ----
#             # Center-based checkpoint
#             if np.isfinite(wmae_c) and (wmae_c < best_center_wmae - 1e-6):
#                 best_center_wmae = wmae_c
#                 best_center_epoch = epoch
#                 pinn_model.save_weights(best_center_path)
#                 logger.info(f"[ckpt] New BEST center WMAE_dir={wmae_c:.1f}° at epoch {epoch} -> {best_center_path}")

#             # Boundary-mean-based checkpoint
#             if np.isfinite(wmae_b) and (wmae_b < best_boundary_wmae - 1e-6):
#                 best_boundary_wmae = wmae_b
#                 best_boundary_epoch = epoch
#                 pinn_model.save_weights(best_boundary_path)
#                 logger.info(f"[ckpt] New BEST boundary WMAE_dir={wmae_b:.1f}° at epoch {epoch} -> {best_boundary_path}")

#             # (Optional) print summary line
#             logger.info(f"[eval@{epoch}] center WMAE_dir={wmae_c:.1f}° (n={met_c['n']}), "
#                         f"boundary WMAE_dir={wmae_b:.1f}° (n={met_b['n']})")

#             '''
#             At the end of training you’ll still save the final weights as you already do, plus you’ll have:
#             …best_center.weights.h5 — best on center WMAE_dir
#             …best_boundary.weights.h5 — best on boundary-mean WMAE_dir

#             If our target is internal fidelity (predicting inside the structure at specific points), load best_center
#             If we care more about matching the boundary aggregate, use best_boundary.
#             If we want a single "champion", pick the one with the lower WMAE_dir,
#                   and use RMSE_speed as a tie-breaker (lower is better).
#             '''

#     # -----------------------------
#     # Save model & normalization
#     # -----------------------------
#     if not args.model_fname.endswith('.weights.h5'):
#         args.model_fname = f'{args.model_fname}.weights.h5'

#     # Final model save path in experiment directory
#     final_model_path = os.path.join(experiment_dir, os.path.basename(args.model_fname))
#     logger.info(f'Saving model: {final_model_path}')
#     pinn_model.save_weights(final_model_path)

#     normalization_meta = {
#         "x_min": float(x_min), "x_max": float(x_max),
#         "y_min": float(y_min), "y_max": float(y_max),
#         "t_min": float(t_min), "t_max": float(t_max)
#     }

#     # Save JSON files in experiment directory
#     normalization_path = os.path.join(experiment_dir, f"{os.path.basename(args.model_fname)}.normalization.json")
#     run_config_path = os.path.join(experiment_dir, f"{os.path.basename(args.model_fname)}.run.json")

#     with open(normalization_path, "w") as f:
#         json.dump(normalization_meta, f)
#     with open(run_config_path, "w") as f:
#         json.dump({**vars(args), "lam0": float(lam0.numpy())}, f, indent=2)


#     # -----------------------------
#     # Predictions for plotting (aggregate over boundary points per sampled time)
#     # -----------------------------
#     inputs_b = tf.concat([x_b_tf, y_b_tf, t_b_tf], axis=1)
#     uv_pred_all = pinn_model(inputs_b).numpy()

#     B = N_boundary_points
#     u_pred_t = uv_pred_all[:, 0:1].reshape(-1, B).mean(axis=1, keepdims=True)  # (N_b_time,1)
#     v_pred_t = uv_pred_all[:, 1:2].reshape(-1, B).mean(axis=1, keepdims=True)

#     u_true_t = u_edge_sampled
#     v_true_t = v_edge_sampled
#     # Use north-positive v for direction reconstruction
#     v_true_n = -v_true_t
#     v_pred_n = -v_pred_t
#     timestamps_sampled = ts_aligned[idx_sample].reshape(-1, 1)

#     speed_true = np.sqrt(u_true_t**2 + v_true_t**2)
#     dir_true = (270 - np.rad2deg(np.arctan2(v_true_n, u_true_t))) % 360

#     speed_pred = np.sqrt(u_pred_t**2 + v_pred_t**2)
#     dir_pred = (270 - np.rad2deg(np.arctan2(v_pred_n, u_pred_t))) % 360

#     # --- Quick metrics: speed RMSE + direction MAE (degrees) ---
#     def dir_from_uv(u, v):
#         # your v is south-positive; convert to north-positive for met direction
#         v_north = -v
#         return (270.0 - np.degrees(np.arctan2(v_north, u))) % 360.0

#     def circ_diff_deg(a, b):
#         # shortest signed angular difference in degrees (-180..180]
#         d = (a - b + 180.0) % 360.0 - 180.0
#         return d

#     def report_metrics(u_pred, v_pred, u_true, v_true, label="",
#                    dir_mask_speed=None, print_line=True, logger=None):
#         # to numpy, column shape
#         u_pred = np.asarray(u_pred).reshape(-1, 1)
#         v_pred = np.asarray(v_pred).reshape(-1, 1)
#         u_true = np.asarray(u_true).reshape(-1, 1)
#         v_true = np.asarray(v_true).reshape(-1, 1)

#         sp_pred = np.sqrt(u_pred**2 + v_pred**2).ravel()
#         sp_true = np.sqrt(u_true**2 + v_true**2).ravel()

#         # base scalar metrics
#         rmse_u = float(np.sqrt(np.mean((u_pred - u_true)**2)))
#         rmse_v = float(np.sqrt(np.mean((v_pred - v_true)**2)))
#         rmse_speed = float(np.sqrt(np.mean((sp_pred - sp_true)**2)))
#         mae_speed  = float(np.mean(np.abs(sp_pred - sp_true)))

#         # masking for direction metrics
#         if dir_mask_speed is None:
#             mask = np.ones_like(sp_true, dtype=bool)
#         else:
#             mask = (sp_true > dir_mask_speed) & (sp_pred > dir_mask_speed)

#         n_dir = int(mask.sum())
#         if n_dir == 0:
#             mae_dir = float("nan")
#             mae_dir_weighted = float("nan")
#         else:
#             dir_pred = dir_from_uv(u_pred[mask], v_pred[mask])
#             dir_true = dir_from_uv(u_true[mask], v_true[mask])
#             ang_err = np.abs(circ_diff_deg(dir_pred, dir_true)).ravel()

#             # unweighted MAE
#             mae_dir = float(np.mean(ang_err))

#             # true-speed-weighted MAE (weights sum to 1)
#             w = sp_true[mask].ravel()
#             w = w / (w.sum() + 1e-12)
#             mae_dir_weighted = float(np.sum(w * ang_err))

#         if print_line:
#             if dir_mask_speed is None:
#                 mask_txt = ""
#             else:
#                 mask_txt = f" (>{dir_mask_speed} m/s, n={n_dir})"
#             message = (f"{label} RMSE_u={rmse_u:.3f} m/s  RMSE_v={rmse_v:.3f} m/s  "
#                       f"RMSE_speed={rmse_speed:.3f} m/s  MAE_speed={mae_speed:.3f} m/s  "
#                       f"MAE_dir={mae_dir:.1f}°  WMAE_dir={mae_dir_weighted:.1f}°{mask_txt}")
#             if logger:
#                 logger.info(message)
#             else:
#                 print(message)

#         return {
#             "RMSE_u": rmse_u,
#             "RMSE_v": rmse_v,
#             "RMSE_speed": rmse_speed,
#             "MAE_speed": mae_speed,
#             "MAE_dir": mae_dir,
#             "WMAE_dir": mae_dir_weighted, #true-speed–weighted direction MAE
#             "n_dir": n_dir,
#         }

#     # Boundary-mean (what you plot)
#     report_metrics(u_pred_t, v_pred_t, u_true_t, v_true_t,
#                label="Boundary-mean", dir_mask_speed=args.dir_mask_speed, logger=logger)


#     # --- Truth at the center (numpy) ---
#     u_c_true = u_sensor_tf.numpy()   # shape (N_b_time, 1)
#     v_c_true = v_sensor_tf.numpy()


#     # Interior CENTER sensor (same times you sampled)
#     inputs_sensor = tf.concat([x_sensor_tf, y_sensor_tf, t_sensor_tf], axis=1)
#     uv_sensor_pred = pinn_model(inputs_sensor).numpy()
#     u_c_pred = uv_sensor_pred[:, 0:1]
#     v_c_pred = uv_sensor_pred[:, 1:2]
#     report_metrics(u_c_pred, v_c_pred, u_c_true, v_c_true,
#                label="Center sensor", dir_mask_speed=args.dir_mask_speed, logger=logger)

#     # for boundary-mean series
#     speed_true_b = np.sqrt(u_true_t**2 + v_true_t**2).ravel()
#     speed_pred_b = np.sqrt(u_pred_t**2 + v_pred_t**2).ravel()
#     mask_b = (speed_true_b > args.dir_mask_speed) & (speed_pred_b > args.dir_mask_speed)

#     n_b = int(mask_b.sum())
#     if n_b == 0:
#         dir_true_b_all = dir_from_uv(u_true_t, v_true_t)
#         dir_pred_b_all = dir_from_uv(u_pred_t, v_pred_t)
#         mae_dir_b = float(np.mean(np.abs(circ_diff_deg(dir_pred_b_all, dir_true_b_all))))
#         logger.info(f"Boundary-mean direction MAE (>{args.dir_mask_speed} m/s): n=0; fallback unmasked={mae_dir_b:.1f}°")
#     else:
#         dir_true_b = dir_from_uv(u_true_t[mask_b], v_true_t[mask_b])
#         dir_pred_b = dir_from_uv(u_pred_t[mask_b], v_pred_t[mask_b])
#         mae_dir_b = float(np.mean(np.abs(circ_diff_deg(dir_pred_b, dir_true_b))))
#         logger.info(f"Boundary-mean direction MAE (masked>{args.dir_mask_speed} m/s): {mae_dir_b:.1f}°  (n={mask_b.sum()})")

#     # for center sensor series (use your center arrays):
#     # u_c_true, v_c_true from sensor; u_c_pred, v_c_pred from model at center
#     # the key is that u_c_true/v_c_true and u_c_pred/v_c_pred are aligned to the
#     # same sampled timestamps (idx_sample) and the center (x,y) location
#     speed_true_c = np.sqrt(u_c_true**2 + v_c_true**2).ravel()
#     speed_pred_c = np.sqrt(u_c_pred**2 + v_c_pred**2).ravel()
#     mask_c = (speed_true_c > args.dir_mask_speed) & (speed_pred_c > args.dir_mask_speed)

#     n_c = int(mask_c.sum())
#     if n_c == 0:
#         dir_true_c_all = dir_from_uv(u_c_true, v_c_true)
#         dir_pred_c_all = dir_from_uv(u_c_pred, v_c_pred)
#         mae_dir_c = float(np.mean(np.abs(circ_diff_deg(dir_pred_c_all, dir_true_c_all))))
#         logger.info(f"Center direction MAE (>{args.dir_mask_speed} m/s): n=0; fallback unmasked={mae_dir_c:.1f}°")
#     else:
#         # Apply the calm mask and compute the masked direction MAE
#         dir_true_c = dir_from_uv(u_c_true[mask_c], v_c_true[mask_c])
#         dir_pred_c = dir_from_uv(u_c_pred[mask_c], v_c_pred[mask_c])
#         mae_dir_c = float(np.mean(np.abs(circ_diff_deg(dir_pred_c, dir_true_c))))
#         logger.info(f"Center direction MAE (masked>{args.dir_mask_speed} m/s): {mae_dir_c:.1f}°  (n={mask_c.sum()})")

#     # --- Plots ---
#     plt.figure(figsize=(12, 5))
#     plt.scatter(timestamps_sampled, speed_true, label='True Speed (m/s)')
#     plt.scatter(timestamps_sampled, speed_pred, linestyle='dashed', label='Predicted Speed (m/s)')
#     plt.xlabel("Timestamp")
#     plt.ylabel("Wind Speed (m/s)")
#     plt.title("Wind Speed Comparison (aggregated over boundary)")
#     plt.legend(); plt.tight_layout();
#     plt.savefig(os.path.join(experiment_dir, "speed_vs_time.png"), dpi=150)
#     plt.close()

#     plt.figure(figsize=(12, 5))
#     plt.scatter(timestamps_sampled, dir_true, label='True Direction (°)')
#     plt.scatter(timestamps_sampled, dir_pred, linestyle='dashed', label='Predicted Direction (°)')
#     plt.xlabel("Timestamp")
#     plt.ylabel("Wind Direction (°)")
#     plt.title("Wind Direction Comparison (aggregated over boundary)")
#     plt.legend(); plt.tight_layout();
#     plt.savefig(os.path.join(experiment_dir, "dir_vs_time.png"), dpi=150)
#     plt.close()

#     # Vector plot over time (aggregated)
#     # downsample
#     step = max(1, len(timestamps_sampled)//200)
#     # flatten to 1-D for quiver
#     t_sub = timestamps_sampled[::step].ravel()
#     u_pred_sub = u_pred_t[::step].ravel()
#     v_pred_sub = v_pred_t[::step].ravel()
#     u_true_sub = u_true_t[::step].ravel()
#     v_true_sub = v_true_t[::step].ravel()

#     # speeds and normalized directions
#     speed_pred_sub = np.sqrt(u_pred_sub**2 + v_pred_sub**2)
#     speed_true_sub = np.sqrt(u_true_sub**2 + v_true_sub**2)

#     u_pred_norm = u_pred_sub / (speed_pred_sub + 1e-8)
#     v_pred_norm = v_pred_sub / (speed_pred_sub + 1e-8)
#     u_true_norm = u_true_sub / (speed_true_sub + 1e-8)
#     v_true_norm = v_true_sub / (speed_true_sub + 1e-8)

#     # two y-rows: predicted on +0.1, true on -0.1
#     y_pred = np.full_like(t_sub, 0.1, dtype=float)
#     y_true = np.full_like(t_sub, -0.1, dtype=float)
#     scale = 0.2

#     # shared color normalization + single colorbar
#     vmax = float(max(np.max(speed_pred_sub), np.max(speed_true_sub), 0.0))
#     norm = mcolors.Normalize(vmin=0.0, vmax=vmax)

#     fig, ax = plt.subplots(figsize=(14, 5))
#     q1 = ax.quiver(t_sub, y_pred, u_pred_norm, v_pred_norm, speed_pred_sub,
#                angles='xy', scale_units='xy', scale=scale, cmap='Reds', norm=norm)
#     q2 = ax.quiver(t_sub, y_true, u_true_norm, v_true_norm, speed_true_sub,
#                angles='xy', scale_units='xy', scale=scale, cmap='Blues', norm=norm, alpha=0.6)

#     fig.colorbar(q1, ax=ax, label='Wind speed (m/s)')  # single colorbar

#     # clean legend using proxies
#     ax.legend(handles=[
#         Line2D([0],[0], color='red', lw=3, label='Predicted'),
#         Line2D([0],[0], color='blue', lw=3, label='True'),
#     ], loc='upper right')

#     ax.set_xlabel("Timestamp")
#     ax.set_ylabel("Wind vector (normalized dir)")
#     ax.set_title("Wind Vectors Over Time (boundary-mean)")
#     fig.tight_layout()
#     fig.savefig(os.path.join(experiment_dir, "quiver.png"), dpi=150)
#     plt.close(fig)

#     # Optional: training curves
#     plt.figure(figsize=(10,4))
#     plt.plot(loss_hist, label='Total')
#     plt.plot(phys_hist, label='Physics')
#     plt.plot(data_hist, label='Data')
#     plt.xlabel('Epoch')
#     plt.ylabel('Loss')
#     plt.title('Training Losses')
#     plt.legend()
#     plt.tight_layout()
#     plt.savefig(os.path.join(experiment_dir, "training_losses.png"), dpi=150)
#     plt.close()

#     # -----------------------------
#     # Experiment complete - summary of outputs
#     # -----------------------------
#     logger.info(f"\n=== Experiment Complete ===")
#     logger.info(f"All outputs saved to: {experiment_dir}")
#     logger.info(f"Contents:")
#     logger.info(f"  - Model weights: {os.path.basename(final_model_path)}")
#     logger.info(f"  - Best center checkpoint: {os.path.basename(best_center_path)}")
#     logger.info(f"  - Best boundary checkpoint: {os.path.basename(best_boundary_path)}")
#     logger.info(f"  - Normalization metadata: {os.path.basename(normalization_path)}")
#     logger.info(f"  - Run configuration: {os.path.basename(run_config_path)}")
#     logger.info(f"  - Plots: speed_vs_time.png, dir_vs_time.png, quiver.png, training_losses.png")
#     logger.info(f"  - Log file: experiment.log")


# if __name__ == "__main__":
#     main()
