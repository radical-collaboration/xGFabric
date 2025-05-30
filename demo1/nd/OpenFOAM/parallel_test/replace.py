import sys

filepath = sys.argv[1]
file_future_path = sys.argv[2]
f = open(filepath, "rt")
text = f.read()
if len(sys.argv) % 2 != 1:
    raise Exception(f"wrong arguments {sys.argv}")
for i in range(3, len(sys.argv), 2):
    text = text.replace(sys.argv[i], sys.argv[i+1])

f.close()
with open(file_future_path, "wt") as f:
    f.write(text)
