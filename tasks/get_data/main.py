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

from ..common.communicator import CommunicatorOpen, PyStorage


def tk_get_data(config):
    env = register_task(config, "get_data", 0)
    logger = register_log(env, logging.INFO)

    # Use senspot to download env['CSPOT_LIMIT']

    data_source = WooF(name=env["CSPOT_ENDPOINT"])

    # get latest.
    latest = data_source.WooFGet(str)
    latest_seq = latest.seq_no

    points = int(env["CSPOT_LIMIT"])
    items = data_source.WooFGets(str, items=points, seq_no=latest_seq - points)

    # Now, format.
    wind_data = parse(items)
    outputs = strip_cols(wind_data)

    # return val is ignored in DragonHPC backend

    # close and return. Also return output
    close_task(env)
    return env["TK_GET_DATA"], outputs.to_dict(orient="records")
