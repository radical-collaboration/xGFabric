import asyncio
import time


async def tk_to_edge(*arg, **kwargs):
    print(f"Hello from to_edge: {__name__} ARGS: {arg}  KWARGS: {kwargs}")
    return time.time()
