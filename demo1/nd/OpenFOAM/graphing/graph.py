import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

df = pd.read_csv("data.csv")

anvil_speedup = df[df["Cluster"] == "ANVIL"]
nd_speedup = df[df["Cluster"] == "ND"]

# Run 1:
run_1 = anvil_speedup[anvil_speedup["Run"] == 1]
plt.plot(run_1["Cores"], run_1["Computation Time"], marker='o')
plt.xlabel("Number of Cores")
plt.ylabel("Time to Compute (s)")
plt.title("Cores vs. Computation Time")
plt.grid()
plt.show()
plt.savefig("graphs/graph.png", bbox_inches="tight")

plt.close()

# Aggregate:
agg = anvil_speedup.groupby("Cores")["Computation Time"].mean().reset_index()
plt.plot(agg["Cores"], agg["Computation Time"], marker='o')
plt.xlabel("Number of Cores")
plt.ylabel("Time to Compute (s)")
plt.title("Cores vs. Computation Time")
plt.grid()
plt.show()
plt.savefig("graphs/Aggregate graph.png", bbox_inches="tight")

plt.close()

# box and whiskers plot:
plt.figure(figsize=(10, 6))
sns.boxplot(x="Cores", y="Computation Time", data=anvil_speedup, width=0.2)
plt.xlabel("Number of Cores")
plt.ylabel("Time to Compute (s)")
plt.title("Cores vs. Computation Time")
plt.grid(True)
# plt.tight_layout()
plt.show()
plt.savefig("graphs/box and whiskers.png", bbox_inches="tight")