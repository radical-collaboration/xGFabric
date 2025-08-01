output = []
with open("data/result_time_nodes_64") as file:
    length = len(file.readlines())
    file.seek(0, 0)
    nodes = int(input("How many nodes? "))
    for i in range(length):
        line = file.readline().strip()
        if f"{nodes} nodes" in line:
            arr = line.split(" ")
            print(f"Computation time: {arr[-4]} Total time: {arr[-8]}")
            output.append(f"{arr[-4]} {arr[-8]}")
print(len(output))