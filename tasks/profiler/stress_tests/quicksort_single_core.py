import random
import sys
import time


def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)


def main(length):
    print("Generating 5 million random integers...")
    arr = [random.randint(0, length) for _ in range(length)]
    print("Sorting...")
    start = time.time()
    sorted_arr = quicksort(arr)
    end = time.time()
    print(f"Sorted in {end - start:.2f} seconds")


if __name__ == "__main__":
    main(int(sys.argv[1]))
