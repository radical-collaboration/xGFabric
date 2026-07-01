# Fetch data from cspot

import os
import logging
import time
import random

from ..common.pyspot.pyspot.senspot import FileWooF, FileWooFItem

logger = logging.getLogger(__name__)


async def tk_to_edge(config, incoming_model, model_name) -> FileWooFItem:
    model = incoming_model

    logger.info(f"Task to_edge fired: {time.time()}.")

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
    return result
