import pandas as pd


def strip_cols(df: pd.DataFrame):

    wind_speeds = pd.to_numeric(df["wind_speed"], errors="coerce").dropna()
    wind_dirs = pd.to_numeric(df["wind_dir"], errors="coerce").fillna(0)

    # params_df = pd.DataFrame({"wind_speed": wind_speeds, "wind_dir": wind_dirs})
    df["wind_speed"] = wind_speeds.round(1)
    df["wind_dir"] = wind_dirs.round(0)

    return df
