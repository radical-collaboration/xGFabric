#!/usr/bin/env python3

import argparse
import asyncio
import inspect
import cloudpickle


async def execute(payload_path: str):
    with open(payload_path, "rb") as f:
        payload = cloudpickle.load(f)

    func = cloudpickle.load(payload["func"])
    if inspect.iscoroutinefunction(func):
        await func(
            payload["in_data"],
            **payload.get("kwargs", {}),
        )
    else:
        func(
            payload["in_data"],
            **payload.get("kwargs", {}),
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("payload")

    args = parser.parse_args()

    asyncio.run(
        execute(
            args.payload,
        )
    )


if __name__ == "__main__":
    main()
