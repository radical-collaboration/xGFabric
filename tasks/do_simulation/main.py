import asyncio
import time


async def tk_do_simulation(*arg, **kwargs):
    print(f"Hello from simulation: {__name__} ARGS: {arg}  KWARGS: {kwargs}")
    return time.time()
