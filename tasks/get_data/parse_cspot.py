#!/usr/bin/env python3
"""
Parse CSPOT data
"""

import sys
from datetime import datetime
from ..common.pyspot.pyspot.senspot import WooFItem
import pandas as pd


def parse(items: list[WooFItem]):
    out = []
    for item in items:
        fields = item.data.split(":")
        windspeed = float(fields[3]) * 0.44704  # mph -> m/s
        windavg = float(fields[4]) * 0.44704  # mph -> m/s
        winddir = float(fields[5])
        out.append((item.timestamp, windspeed, windavg, winddir))

    df = pd.DataFrame(out, columns=["dt", "wind_speed", "wind_avg", "wind_dir"])

    return df
