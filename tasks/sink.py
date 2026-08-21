import asyncio

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask, TypedData

from .common.dtypes import *
import logging
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


def graph(data, fname, model_name, z, w):

    plt.figure(figsize=(6, 5))

    # Plot heatmap
    im = plt.imshow(data, cmap="viridis", origin="lower", vmin=0, vmax=2.5)

    # Add colorbar
    plt.colorbar(im)

    # Optional labels
    plt.title(f"Heatmap of {model_name} at Z={z}, W={round(w,3)}")
    plt.xlabel("X")
    plt.ylabel("Y")

    # Save image
    plt.savefig(fname, dpi=300, bbox_inches="tight")

    plt.close()


class CUPS_Sink(UtilityTask):
    def __init__(self, flow: WorkflowEngine, config):
        super().__init__(flow)
        self.flow = flow
        self.config = config

    async def main_loop(self, runtime, in_data: TypedData):
        print(f"Received Inference: {in_data.data['arch']}")

        if in_data.data["arch"] == "na":
            print("No surrogate ready yet")
            return

        # create graph

        fname = self.config["PLAYGROUND_DIR"] + "/out.png"

        graph(
            in_data.data["result"][1],
            fname,
            in_data.data["arch"],
            3,
            w=in_data.data["w"],
        )
        print("\n\n" + "=" * 30 + "\n" + str(fname) + "\n" + "=" * 30)
