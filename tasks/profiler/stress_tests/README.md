# System Benchmark & Stress Test Suite

This directory is from repository: 
https://github.com/obi-wan-shinobi/Stress-test 
MIT License. Author: Obi-wan-shinobi

This repository contains a collection of Python scripts for benchmarking and stress-testing various aspects of your system, including CPU, memory, disk I/O, and multicore performance. It also includes a sophisticated all-in-one stress test (`stress2.py`) with advanced monitoring and reporting features.

## Features

- **CPU Benchmarking**: Matrix multiplication, prime counting, and quicksort (single and multicore).
- **Memory Bandwidth Benchmarking**: Vectorized memory operations.
- **Disk I/O Benchmarking**: Sequential write/read speed tests.
- **Multicore Stress Testing**: Parallel sorting and prime counting.
- **Comprehensive Stress Test**: `stress2.py` provides advanced stress testing with logging, monitoring, and reporting.

## Scripts Overview

| Script                        | Description                                 |
|-------------------------------|---------------------------------------------|
| `CPU-Intensive_Benchmark.py`  | Matrix multiplication CPU benchmark         |
| `Diskio.py`                   | Disk I/O write/read speed test              |
| `mbb.py`                      | Memory bandwidth benchmark                  |
| `Multicore_CPU_Stress_Test.py`| Multicore CPU prime counting                |
| `multicore.py`                | Parallel sort using all CPU cores           |
| `quicksort_single_core.py`    | Single-core quicksort benchmark             |
| `stress.py`                   | Full system stress test (CPU, RAM, Disk)    |
| `stress2.py`                  | Advanced stress test with monitoring/report |

## Requirements

- Python 3.8+
- Recommended: Run in a virtual environment

### Python Packages

- numpy
- psutil
- GPUtil (for GPU info, optional)

Install requirements with:

```bash
pip install numpy psutil gputil
```

> **Note:** Some scripts use the `multiprocessing` and `concurrent.futures` modules from the Python standard library.

## Usage

A main entry script (`main.py`) is provided to run any of the benchmarks or stress tests interactively.

### Run the main entry point

```bash
python main.py
```

Follow the prompts to select and run a benchmark or stress test.

---

**Warning:** These scripts can heavily load your system. Save your work and close other applications before running stress tests.

---

## License

MIT License
