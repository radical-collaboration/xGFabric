import asyncio
import time


async def tk_do_pinn(*arg, **kwargs):
    print(f"Hello from pinn: {__name__} ARGS: {arg}  KWARGS: {kwargs}")
    return time.time()
