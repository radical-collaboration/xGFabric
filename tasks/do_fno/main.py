import asyncio
import time


async def tk_do_fno(*arg, **kwargs):
    print(f"Hello from fno: {__name__} ARGS: {arg}  KWARGS: {kwargs}")
    return time.time()
