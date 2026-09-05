"""Terminal component: heatmap of the selected surrogate's wind field.

The heatmap is rendered on the endpoint and returned inline (small PNG
bytes) so the runtime can surface it to the dashboard via
`record_output` -- the DT service has no file staging, and a downscaled
heatmap is well under the return-value cap.  A copy is also written to
XGF_WORKSPACE, but that path is resolved and created *inside* the task
(endpoint-side); the sink's main_loop runs on the broker, a different
host, so it must not build or create that path itself.
"""

import base64

from digitaltwin.components import TypedData, UtilityTask


class ServiceSink(UtilityTask):
    def __init__(self, flow):
        super().__init__(flow)
        self.flow = flow
        self.count = 0

        @flow.function_task
        async def render_heatmap(data, arch, w, count):
            import io
            import os
            from pathlib import Path

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

            # a copy to the endpoint filesystem, for the record -- resolved
            # here (endpoint XGF_WORKSPACE) and best-effort, so a missing or
            # read-only path never fails the field
            try:
                base = Path(os.environ.get("XGF_WORKSPACE", "")
                            or Path.home() / "xgf_twin")
                base.mkdir(parents=True, exist_ok=True)
                fig.savefig(str(base / f"field_{count:04d}_{arch}.png"),
                            dpi=90, bbox_inches="tight")
            except OSError:
                pass

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
        png = await self._render(in_data.data["result"][1], arch,
                                 in_data.data["w"], self.count)

        # surface it to the dashboard -- small enough to ride inline
        b64 = base64.b64encode(png).decode("ascii")
        runtime.record_output(f"field {self.count} ({arch})",
                              f"data:image/png;base64,{b64}")
