#!/usr/bin/env python3
"""Render twin.py's telemetry reports from a service-mode run.

In service mode nobody calls ``flow.start_telemetry`` -- and nobody has
to: the rhapsody plugin on the ENDPOINT records every task and a
resource poll on its own (the ``[telemetry]`` extra), as
``telemetry-output/session.*.telemetry.jsonl`` in the endpoint's
working directory.  This script points twin.py's existing report
generators at those files.

    python service/collect_reports.py [telemetry-dir] [--last N]

``telemetry-dir`` defaults to ``telemetry-output/`` under the local
digital.twins checkout; for a remote endpoint, scp the jsonl files over
first.  Reports land next to the jsonl.

Known gap: the workflow-gantt renders but cannot group per workflow --
service twins do not run inside ``workflow_scope()``, so no
``asyncflow.workflow_id`` is stamped.  Grouping needs engine-side
telemetry in the DT service (a digital.twins feature, not a demo-side
one); the task waterfall / swimlane / resource dashboards are complete
without it.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reports.plot_workflow_dashboard import plot_split
from reports.plot_workflow_gantt import plot as plot_gantt

DEFAULT_DIR = os.path.expanduser("~/radical/digital_twins/telemetry-output")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render reports from endpoint telemetry")
    parser.add_argument("telemetry_dir", nargs="?", default=DEFAULT_DIR)
    parser.add_argument("--last", type=int, default=1,
                        help="how many of the newest sessions to render")
    args = parser.parse_args()

    files = sorted(Path(args.telemetry_dir).glob("*.telemetry.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"no *.telemetry.jsonl under {args.telemetry_dir}",
              file=sys.stderr)
        return 1

    for f in files[:args.last]:
        print(f"== {f.name}")
        plot_split(str(f))
        plot_gantt(f)

    return 0


if __name__ == "__main__":
    sys.exit(main())
