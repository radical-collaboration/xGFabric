import pandas as pd


def strip_cols(df: pd.DataFrame):

    wind_speeds = pd.to_numeric(df["wind_speed"], errors="coerce").dropna()
    wind_dirs = pd.to_numeric(df["wind_dir"], errors="coerce").fillna(0)

    params_df = pd.DataFrame({"wind_speed": wind_speeds, "wind_dir": wind_dirs})
    params_df["wind_speed"] = params_df["wind_speed"].round(1)
    params_df["wind_dir"] = params_df["wind_dir"].round(0)

    return params_df
