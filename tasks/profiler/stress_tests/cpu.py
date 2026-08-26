import sys

import numpy as np
import time


def matrix_multiplication_benchmark(size=2000):
    A = np.random.rand(size, size)
    B = np.random.rand(size, size)

    start = time.time()
    C = np.dot(A, B)
    end = time.time()

    print(
        f"Matrix multiplication of {size}x{size} completed in {end - start:.2f} seconds"
    )


if __name__ == "__main__":
    matrix_multiplication_benchmark(int(sys.argv[1]))
