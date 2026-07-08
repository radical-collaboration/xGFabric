# Fetch data from cspot

import os
import logging
import time
import random
from .parse_cspot import parse
from ..common.log_formatter import register_task, register_log, close_task
import datetime
from .sensor_to_sim_params import strip_cols

from ..common.pyspot.pyspot.senspot import WooF

async def tk_get_data(config):
    env = register_task(config, "get_data", 0)
    logger = register_log(env, logging.INFO)

    # Use senspot to download config['CSPOT_LIMIT']

    data_source = WooF(name=os.getenv("CSPOT_ENDPOINT"))

    # get latest.
    latest = data_source.WooFGet(str)
    latest_seq = latest.seq_no

    points = int(os.getenv("CSPOT_LIMIT"))
    items = data_source.WooFGets(str, items=points, seq_no=latest_seq - points)

    # Now, format.
    wind_data = parse(items)
    outputs = strip_cols(wind_data)

    # return array of filenames of parameters
    close_task(env)
    return outputs.to_dict(orient="records")
