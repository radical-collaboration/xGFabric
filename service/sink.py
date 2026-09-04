"""Terminal component: heatmap of the selected surrogate's wind field.

The heatmap is rendered on the endpoint and returned inline (small PNG
bytes) so the runtime can surface it to the dashboard via
`record_output` -- the DT service has no file staging, and a downscaled
heatmap is well under the return-value cap.  It is also written to
XGF_WORKSPACE on the endpoint for the record (resolved at runtime, since
this module ships by value).
"""

import base64
import os
from pathlib import Path

from digitaltwin.components import TypedData, UtilityTask


def _workspace() -> Path:
    base = Path(os.environ.get("XGF_WORKSPACE", "")
                or Path.home() / "xgf_twin")
    base.mkdir(parents=True, exist_ok=True)
    return base


class ServiceSink(UtilityTask):
    def __init__(self, flow):
        super().__init__(flow)
        self.flow = flow
        self.count = 0

        @flow.function_task
        async def render_heatmap(data, arch, w, fname):
            import io

            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig = plt.figure(figsize=(4, 3.2))
            im = plt.imshow(data, cmap="viridis", origin="lower",
                            vmin=0, vmax=2.5)
            plt.colorbar(im)
            plt.title(f"{arch}  W={round(w, 3)}")
            plt.xlabel("X")
            plt.ylabel("Y")

            # to the endpoint filesystem, for the record
            fig.savefig(fname, dpi=90, bbox_inches="tight")
            # and to memory, small, for the inline return
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=72, bbox_inches="tight")
            plt.close(fig)
            return buf.getvalue()

        self._render = render_heatmap

    async def main_loop(self, runtime, in_data: TypedData):
        arch = in_data.data["arch"]
        print(f"[sink] field from {arch}", flush=True)
        if arch == "na" or not in_data.data.get("result"):
            return

        self.count += 1
        fname = str(_workspace() / f"field_{self.count:04d}_{arch}.png")
        png = await self._render(in_data.data["result"][1], arch,
                                 in_data.data["w"], fname)

        # surface it to the dashboard -- small enough to ride inline
        b64 = base64.b64encode(png).decode("ascii")
        runtime.record_output(f"field {self.count} ({arch})",
                              f"data:image/png;base64,{b64}")
