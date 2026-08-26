import sys
import time
import numpy as np


def memory_bandwidth_benchmark(size):
    # size = 500_000_000  # ~500MB array
    arr = np.zeros(size, dtype=np.float32)

    start = time.time()
    arr += 1  # Vectorized write operation
    end = time.time()

    duration = end - start
    print(
        f"Wrote {arr.nbytes / (1024 ** 2):.2f} MB in {duration:.2f} seconds ({arr.nbytes / (1024 ** 2) / duration:.2f} MB/s)"
    )


if __name__ == "__main__":
    memory_bandwidth_benchmark(int(sys.argv[1]))
