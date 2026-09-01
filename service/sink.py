"""Terminal component: heatmap of the selected surrogate's wind field.

Same output as ``tasks.sink.CUPS_Sink`` -- the workspace resolves at
runtime on the executing host (XGF_WORKSPACE, default the host's home),
because this module ships by value and a client-side path does not exist
where the component runs.
"""

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
        async def save_heatmap(data, arch, w, fname):
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            plt.figure(figsize=(6, 5))
            im = plt.imshow(data, cmap="viridis", origin="lower",
                            vmin=0, vmax=2.5)
            plt.colorbar(im)
            plt.title(f"Heatmap of {arch} at Z=3, W={round(w, 3)}")
            plt.xlabel("X")
            plt.ylabel("Y")
            plt.savefig(fname, dpi=150, bbox_inches="tight")
            plt.close()
            return fname

        self._save = save_heatmap

    async def main_loop(self, runtime, in_data: TypedData):
        arch = in_data.data["arch"]
        print(f"[sink] field from {arch}", flush=True)
        if arch == "na":
            return

        self.count += 1
        fname = str(_workspace() / f"field_{self.count:04d}_{arch}.png")
        await self._save(in_data.data["result"][1], arch,
                         in_data.data["w"], fname)
        print("\n" + "=" * 30 + f"\n{fname}\n" + "=" * 30, flush=True)
