#!/usr/bin/env python3
"""
Convert wind speed + compass bearing to Cartesian x/y components.
x = north component, y = east component.
wd = compass bearing the wind blows TOWARDS (0=N, 90=E).

Prints "ux uy" to stdout with 6 decimal places.

Usage: wind_components.py <wind_speed> <wind_dir_degrees>
"""
import math
import sys


def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    ws = float(sys.argv[1])
    wd = math.radians(float(sys.argv[2]))
    print(f'{ws * math.cos(wd):.6f} {ws * math.sin(wd):.6f}')


if __name__ == "__main__":
    main()
