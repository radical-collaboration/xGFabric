import random
import sys
import time
from multiprocessing import Pool, cpu_count

CHUNK_COUNT = cpu_count()  # Number of processes = number of cores


def sort_chunk(chunk):
    return sorted(chunk)


def parallel_sort(arr):
    # Step 1: Split the array into chunks
    chunk_size = len(arr) // CHUNK_COUNT
    chunks = [arr[i * chunk_size : (i + 1) * chunk_size] for i in range(CHUNK_COUNT)]

    # Add remaining elements to the last chunk
    if len(arr) % CHUNK_COUNT != 0:
        chunks[-1].extend(arr[CHUNK_COUNT * chunk_size :])

    # Step 2: Sort each chunk in a separate process
    with Pool(processes=CHUNK_COUNT) as pool:
        sorted_chunks = pool.map(sort_chunk, chunks)

    # Step 3: Merge sorted chunks (naive merge, better to use heapq.merge)
    from heapq import merge

    sorted_arr = sorted_chunks[0]
    for chunk in sorted_chunks[1:]:
        sorted_arr = list(merge(sorted_arr, chunk))

    return sorted_arr


def main(length):
    print(f"Generating {length:,} random integers...")
    arr = [random.randint(0, length) for _ in range(length)]

    print("Sorting in parallel...")
    start = time.time()
    sorted_arr = parallel_sort(arr)
    end = time.time()

    print(f"Sorted in {end - start:.2f} seconds")


if __name__ == "__main__":
    main(int(sys.argv[1]))
