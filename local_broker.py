"""Standalone stream broker

Addresses come from configuration (`DT_STREAM_PUB_ADDR` /
`DT_STREAM_SUB_ADDR`, loopback defaults)
"""

from digitaltwin.config import stream_addresses
from digitaltwin.streaming import ZMQ_Broker

from dotenv import load_dotenv

load_dotenv("tasks/common/config.sh")


if __name__ == "__main__":
    broker = ZMQ_Broker(*stream_addresses())

    publish_addr, subscribe_addr = broker.bind()
    print(
        f"stream broker: publish to {publish_addr}, subscribe on {subscribe_addr}",
        flush=True,
    )

    broker.run()
