from multiprocessing import Pool, cpu_count
import sys
import time


def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True


def count_primes_in_range(start, end):
    return sum(1 for i in range(start, end) if is_prime(i))


def prime_benchmark(limit=1_000_000):
    print(f"Counting primes up to {limit}...")
    start_time = time.time()

    pool = Pool(cpu_count())
    chunk_size = limit // cpu_count()
    ranges = [(i * chunk_size, (i + 1) * chunk_size) for i in range(cpu_count())]
    results = pool.starmap(count_primes_in_range, ranges)
    pool.close()
    pool.join()

    total_primes = sum(results)
    end_time = time.time()

    print(f"Found {total_primes} primes in {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    prime_benchmark(int(sys.argv[1]))
