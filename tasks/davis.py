import asyncio
import json

from digitaltwin import PubSubConfig, RuntimeAPI
from digitaltwin.components import UtilityTask
from .common.dtypes import *

from tasks.common.log_formatter import register_log
from utils_architecture import register_task

import logging

# try:
#     from pyspot import WooF, WooFItem
# except ImportError:
from .common.pyspot.pyspot import WooF, WooFItem

import pandas as pd


def parse(item: WooFItem):
    out = []
    fields = item.data.split(":")  # type: ignore
    windspeed = float(fields[3]) * 0.44704  # mph -> m/s
    windavg = float(fields[4]) * 0.44704  # mph -> m/s
    winddir = float(fields[5])
    out.append((item.timestamp, windspeed, windavg, winddir))

    df = pd.DataFrame(out, columns=["dt", "wind_speed", "wind_avg", "wind_dir"])

    return df


def strip_cols(df: pd.DataFrame):

    wind_speeds = pd.to_numeric(df["wind_speed"], errors="coerce").dropna()
    wind_dirs = pd.to_numeric(df["wind_dir"], errors="coerce").fillna(0)

    # params_df = pd.DataFrame({"wind_speed": wind_speeds, "wind_dir": wind_dirs})
    df["wind_speed"] = wind_speeds.round(1)
    df["wind_dir"] = wind_dirs.round(0)

    return df


class DavisWind(UtilityTask):
    def __init__(self, flow, config: dict):
        super().__init__(flow)
        self.flow = flow

        self.config = config

        # @self.flow.function_task
        async def sensor_loop(config, stream_config: PubSubConfig):
            psclient = await stream_config.connect()
            register_task(config, "", "", "DavisWind", 0)
            logger = register_log(config)

            # Use senspot to download env['CSPOT_LIMIT']

            while True:
                try:
                    data_source = WooF(name=config["CSPOT_ENDPOINT"])

                    # get latest.
                    latest = data_source.WooFGet(str)
                except OSError:
                    logger.info("CSPOT fetch failed... Try again...")
                    await asyncio.sleep(5)
                    continue

                if latest is None:
                    logger.info("CSPOT fetch failed... Try again...")
                    await asyncio.sleep(5)
                    continue

                # Now, format.
                wind_data = parse(latest)  # type: ignore
                outputs = strip_cols(wind_data)
                logger.info(
                    f"Davis emit: {json.dumps(outputs.to_dict(orient='records'), indent=1, default=lambda o: str(o))}"
                )
                await psclient.publish(
                    DAVIS_WIND_SENSOR, outputs.to_dict(orient="records")[0]
                )
                await asyncio.sleep(1)

        self.sensor_loop = sensor_loop

    async def main_loop(self, runtime: RuntimeAPI, in_data):
        await self.sensor_loop(self.config, runtime.stream_config)
