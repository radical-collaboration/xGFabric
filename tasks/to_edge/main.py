# Fetch data from cspot

import os
import logging
import time
import random
from ..common.log_formatter import register_task, register_log, close_task
import datetime

from ..common.pyspot.pyspot.senspot import FileWooF, FileWooFItem

logger = logging.getLogger(__name__)


async def tk_to_edge(config, incoming_model, model_name) -> FileWooFItem:
    env = register_task(config, "to_edge", model_name)
    logger = register_log(env, logging.INFO)
    # create directory for sims

    model = incoming_model

    # Use senspot to upload file to endpoint

    if model_name == "pcr":
        endpoint = os.getenv("PCR_ENDPOINT")
    elif model_name == "fno":
        endpoint = os.getenv("FNO_ENDPOINT")
    elif model_name == "pinn":
        endpoint = os.getenv("PINN_ENDPOINT")

    target = FileWooF(endpoint)
    result = target.send(model)

    # return array of filenames of parameters
    close_task(env)
    return result
