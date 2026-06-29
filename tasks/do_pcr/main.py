import asyncio
import time


async def tk_do_pcr(*arg, **kwargs):
    print(f"Hello from pcr: {__name__} ARGS: {arg}  KWARGS: {kwargs}")
    return time.time()
