# Fetch data from cspot

import os
import logging
import time
import random
from .parse_cspot import parse
from .sensor_to_sim_params import strip_cols

from ..common.pyspot.pyspot.senspot import WooF

logger = logging.getLogger(__name__)


async def tk_get_data(config):
    my_unique_id = str(random.randint(0, 40000))

    logger.info(
        f"Task get_data fired: {time.time()}. Unique ID: {my_unique_id}. Called by: {config['PARENT_UNIQUE_ID']}"
    )

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

    print(f"OUTPUT: {outputs}")

    # return array of filenames of parameters
    return my_unique_id, outputs.to_dict(orient="records")
