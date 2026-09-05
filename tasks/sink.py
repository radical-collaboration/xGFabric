"""Terminal component: heatmap of the selected surrogate's wind field.

The heatmap renders on the endpoint and is returned inline (small PNG
bytes) so the runtime can surface it to the dashboard via
`record_output` -- the DT service has no file staging, and a downscaled
heatmap is well under the return-value cap.  It is also written to
PLAYGROUND_DIR on the endpoint for the record.

matplotlib is imported lazily inside the task body (which runs on the
endpoint) so packaging/instantiating this class on the client and broker
does not need it.
"""

import base64
import os

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask, TypedData

from .common.dtypes import *
import logging

logger = logging.getLogger(__name__)


class CUPS_Sink(UtilityTask):
    def __init__(self, flow: WorkflowEngine, config):
        super().__init__(flow)
        self.flow = flow
        self.config = config
        self.count = 0

        @self.flow.function_task
        async def render(field, arch, w, fname):
            import io

            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig = plt.figure(figsize=(4, 3.2))
            im = plt.imshow(field, cmap="viridis", origin="lower",
                            vmin=0, vmax=2.5)
            plt.colorbar(im)
            plt.title(f"{arch}  W={round(w, 3)}")
            plt.xlabel("X")
            plt.ylabel("Y")

            if fname:
                os.makedirs(os.path.dirname(fname), exist_ok=True)
                fig.savefig(fname, dpi=150, bbox_inches="tight")
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=72, bbox_inches="tight")
            plt.close(fig)
            return buf.getvalue()

        self._render = render

    async def main_loop(self, runtime, in_data: TypedData):
        arch = in_data.data["arch"]
        print(f"Received Inference: {arch}")

        if arch == "na" or not in_data.data.get("result"):
            print("No surrogate ready yet")
            return

        self.count += 1
        fname = os.path.join(self.config.get("PLAYGROUND_DIR", "."),
                             f"out_{self.count:04d}.png")
        png = await self._render(in_data.data["result"][1], arch,
                                 in_data.data["w"], fname)

        # surface it to the dashboard -- small enough to ride inline
        b64 = base64.b64encode(png).decode("ascii")
        runtime.record_output(f"field {self.count} ({arch})",
                              f"data:image/png;base64,{b64}")
        print("\n" + "=" * 30 + f"\n{fname}\n" + "=" * 30)
