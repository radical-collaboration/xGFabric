#!/usr/bin/env python3
"""Fake Davis wind sensor as an EXTERNAL channel publisher.

In service mode the sensor is not a twin component: it publishes to a
shared channel and the twin binds it with ``add_input`` -- any number of
twins can listen.  The records mirror what ``tasks.davis`` emits
(``strip_cols`` output), at the same 5 s cadence, fake for the same
reason twin.py fakes them.

Environment: DT_STREAM_BACKEND / RADICAL_ORBIT_BROKER_URL(+_CERT) select
the data plane, exactly like every other client-side process.
"""

import asyncio
import datetime
import random

from digitaltwin.streaming import ChannelPublisher

DAVIS_CHANNEL = "xgf/davis"


async def main() -> None:
    publisher = await ChannelPublisher.open(DAVIS_CHANNEL)
    n = 0
    try:
        while True:
            r = random.random()
            record = {
                "dt": datetime.datetime.now().isoformat(),
                "wind_speed": round(r * 20, 1),
                "wind_avg": round(r * 15, 1),
                "wind_dir": round(r * 360),
            }
            await publisher.publish(record)
            n += 1
            if n % 12 == 0:
                print(f"davis: {n} records", flush=True)
            await asyncio.sleep(5)
    finally:
        await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
