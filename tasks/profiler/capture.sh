#!/bin/bash

# Repeat 100 times

output_file=$1

echo "t_seconds,cpu_seconds,disk_read,disk_write,sys_read,sys_write,memory_bytes" > $output_file


for i in {1..100}; do
  echo "CPU Intensive Benchmark: $i / 100"
  python3 profiler.py --csv --exe "python3 stress_tests/cpu.py $(( i * 20 ))" >> $output_file
done

for i in {1..100}; do
  echo "Disk: $i / 100"
  python3 profiler.py --csv --exe "python3 stress_tests/disk.py $(( i * 512 ))" >> $output_file
done

for i in {1..128}; do
  echo "Mem Bandwidth: $i / 128"
  python3 profiler.py --csv --exe "python3 stress_tests/mbb.py $(( i * 1048576 ))" >> $output_file
done

for i in {1..100}; do
  echo "Multi Prime: $i / 100"
  python3 profiler.py --csv --exe "python3 stress_tests/multi_prime.py $(( i * 10000 ))" >> $output_file
done

for i in {1..128}; do
  echo "Multi Core: $i / 128"
  python3 profiler.py --csv --exe "python3 stress_tests/multicore.py $(( i * 256 ))" >> $output_file
done

for i in {1..100}; do
  echo "Quick Sort: $i / 100"
  python3 profiler.py --csv --exe "python3 stress_tests/quicksort_single_core.py $(( i * 256 ))" >> $output_file
done
