"""In-process resource profiling of an inference call.

Approach (1) from the profiler discussion: instead of cloudpickling the
inference function to a file and running the standalone ``profiler.py``
under a fresh process group, run the call in-process and read the
process's own resource counters around it.  This runs entirely where the
task runs (the endpoint) -- no file hand-off between the executable-task
command-builder (broker) and the command (endpoint), which is what the
subprocess profiler needed a shared filesystem for.

Trade-off vs the subprocess profiler: no process-group isolation, so the
numbers include a little of the task runner's own activity during the
call, and ``memory_bytes`` is the process peak RSS (a high-water mark)
rather than the child's PSS.  For a *comparative* fingerprint across the
candidate surrogates -- which is all the selector needs -- that is fine.

The returned dict keeps the exact keys and order the subprocess profiler
emitted, so ``data.csv`` and ``endpoint_trainer.py`` are unchanged.
"""

import os
import resource
import time

import cloudpickle
import psutil


def load_callable(blob):
    """Reconstruct the inference callable the agent cloudpickled."""
    obj = cloudpickle.loads(blob)
    # the agent ships either the raw callable or the {"func": ...} payload
    if isinstance(obj, dict) and "func" in obj:
        obj = obj["func"]
    return obj


async def profile_call(func, example_data, kwargs=None) -> dict:
    """Run ``func(example_data, **kwargs)`` once and measure its cost.

    Returns the profiler's schema:
      total_seconds, cpu_seconds, disk_read_bytes, disk_write_bytes,
      sys_read_bytes, memory_bytes
    """

    kwargs = kwargs or {}
    proc = psutil.Process(os.getpid())

    try:
        io0 = proc.io_counters()
    except Exception:
        io0 = None
    ru0 = resource.getrusage(resource.RUSAGE_SELF)
    t0 = time.perf_counter()

    result = func(example_data, **kwargs)
    if hasattr(result, "__await__"):
        await result

    wall = time.perf_counter() - t0
    ru1 = resource.getrusage(resource.RUSAGE_SELF)
    try:
        io1 = proc.io_counters()
    except Exception:
        io1 = None

    def io_delta(attr):
        if io0 is None or io1 is None:
            return 0
        return max(0, getattr(io1, attr, 0) - getattr(io0, attr, 0))

    return {
        "total_seconds": wall,
        "cpu_seconds": (ru1.ru_utime - ru0.ru_utime)
                       + (ru1.ru_stime - ru0.ru_stime),
        "disk_read_bytes": io_delta("read_bytes"),
        "disk_write_bytes": io_delta("write_bytes"),
        "sys_read_bytes": io_delta("read_chars"),
        # ru_maxrss is peak RSS in KiB on Linux (bytes on macOS); the peak
        # high-water mark, matching the subprocess profiler's peak metric.
        "memory_bytes": int(ru1.ru_maxrss) * 1024,
    }
