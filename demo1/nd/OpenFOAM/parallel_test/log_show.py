import os
import time
import sys

filename = sys.argv[1]

with open(filename, "rt") as f:
    lines = f.readlines()

print("\n"*20)
print("Script started ...")
input()
for line in lines:
    print(line, end="")
    time.sleep(0.1)

