#!/usr/bin/env python3
"""
extract_timing.py - Parse pipeline_metrics.json and print a timing summary.

Usage:
    python3 extract_timing.py <pipeline_metrics.json> [--iterations N]

    # Compare multiple runs side-by-side:
    python3 extract_timing.py results/exp_A/pipeline_metrics.json \
                              results/exp_B/pipeline_metrics.json

The script also accepts a log file (.log / .out / .err) and extracts
wall-clock time from [INFO] HH:MM:SS [TIMER] lines as a cross-check.
"""

import sys
import json
import re
import argparse
from pathlib import Path


def fmt(s: float) -> str:
    s = int(s)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


def load_metrics(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def summary_from_metrics(m, n_iterations=None):
    """Return a flat summary dict from a pipeline_metrics.json object."""
    sections = m.get("sections", {})
    total_s = m.get("total_duration_seconds", 0)

    # Detect number of per-iteration keys if not supplied
    if n_iterations is None:
        n_iterations = sum(
            1 for k in sections if re.fullmatch(r"iteration_\d+", k)
        )

    result = {"total": total_s, "iterations": {}, "models": {}, "phases": {}}

    for i in range(1, n_iterations + 1):
        key = f"iteration_{i}"
        if key in sections:
            result["iterations"][i] = sections[key]["duration_seconds"]

    for model in ("pcr", "pinn", "fno"):
        key = f"training_{model}"
        if key in sections:
            result["models"][model] = sections[key]["duration_seconds"]

    for phase in ("data_acquisition", "simulations", "training", "evaluation"):
        if phase in sections:
            result["phases"][phase] = sections[phase]["duration_seconds"]

    return result


def extract_timing_from_log(log_path):
    """
    Parse [TIMER] lines from a pipeline log to recover section durations.
    Example line:
        [INFO] 14:32:11 [TIMER] iteration_1:   1h 5m 20s
    """
    pattern = re.compile(
        r"\[TIMER\]\s+([\w_]+):\s+"
        r"(?:(\d+)h\s+)?(?:(\d+)m\s+)?(\d+)s"
    )
    durations: dict[str, float] = {}
    with open(log_path) as f:
        for line in f:
            m = pattern.search(line)
            if m:
                sec_name = m.group(1)
                h = int(m.group(2) or 0)
                mins = int(m.group(3) or 0)
                secs = int(m.group(4) or 0)
                durations[sec_name] = h * 3600 + mins * 60 + secs
    return durations


def print_summary(label: str, s: dict) -> None:
    width = 56
    print(f"{'─' * width}")
    print(f"  {label}")
    print(f"{'─' * width}")
    print(f"  {'TOTAL PIPELINE':<38} {fmt(s['total'])}")

    if s["iterations"]:
        print()
        for i, d in sorted(s["iterations"].items()):
            print(f"  {'Iteration ' + str(i):<38} {fmt(d)}")

    if s["models"]:
        print()
        for model, d in s["models"].items():
            label_str = f"Training {model.upper()} (last iter)"
            print(f"  {label_str:<38} {fmt(d)}")

    if s["phases"]:
        print()
        for phase, d in s["phases"].items():
            print(f"  {'Phase: ' + phase:<38} {fmt(d)}")

    print(f"{'─' * width}")


def print_comparison(summaries: list[tuple[str, dict]]) -> None:
    """Print a side-by-side comparison table for multiple runs."""
    labels = [lbl for lbl, _ in summaries]
    col_w = max(len(l) for l in labels)

    # Collect all row keys
    rows: list[tuple[str, str]] = [("total", "TOTAL PIPELINE")]
    for i in range(1, 10):
        if any(i in s["iterations"] for _, s in summaries):
            rows.append((f"iter_{i}", f"Iteration {i}"))
    for model in ("pcr", "pinn", "fno"):
        if any(model in s["models"] for _, s in summaries):
            rows.append((f"model_{model}", f"Training {model.upper()}"))
    for phase in ("data_acquisition", "simulations", "training", "evaluation"):
        if any(phase in s["phases"] for _, s in summaries):
            rows.append((f"phase_{phase}", f"Phase: {phase}"))

    header_row_lbl = 38
    print()
    print(f"  {'COMPARISON TABLE'}")
    print(f"  {'─' * (header_row_lbl + (col_w + 3) * len(labels))}")
    header = f"  {'Metric':<{header_row_lbl}}"
    for lbl in labels:
        header += f"  {lbl:>{col_w}}"
    print(header)
    print(f"  {'─' * (header_row_lbl + (col_w + 3) * len(labels))}")

    def get_val(key, s):
        if key == "total":
            return s["total"]
        if key.startswith("iter_"):
            i = int(key.split("_")[1])
            return s["iterations"].get(i)
        if key.startswith("model_"):
            m = key.split("_", 1)[1]
            return s["models"].get(m)
        if key.startswith("phase_"):
            p = key.split("_", 1)[1]
            return s["phases"].get(p)
        return None

    for key, row_label in rows:
        row = f"  {row_label:<{header_row_lbl}}"
        for _, s in summaries:
            val = get_val(key, s)
            cell = fmt(val) if val is not None else "—"
            row += f"  {cell:>{col_w}}"
        print(row)

    print(f"  {'─' * (header_row_lbl + (col_w + 3) * len(labels))}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Extract and display timing from pipeline_metrics.json"
    )
    parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help="pipeline_metrics.json file(s), or pipeline log/err files",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        metavar="N",
        help="Expected number of iterations (auto-detected if omitted)",
    )
    args = parser.parse_args()

    summaries: list[tuple[str, dict]] = []

    for file_str in args.files:
        p = Path(file_str)
        if not p.exists():
            print(f"[ERROR] File not found: {p}", file=sys.stderr)
            sys.exit(1)

        label = p.parent.name or p.name

        if p.suffix == ".json":
            m = load_metrics(p)
            s = summary_from_metrics(m, args.iterations)
        else:
            # Log file — reconstruct summary from [TIMER] lines
            durations = extract_timing_from_log(p)
            if not durations:
                print(f"[WARN] No [TIMER] lines found in: {p}", file=sys.stderr)
                continue
            total_s = durations.get("pipeline_total", 0)
            s = {"total": total_s, "iterations": {}, "models": {}, "phases": {}}
            for k, d in durations.items():
                m2 = re.fullmatch(r"iteration_(\d+)", k)
                if m2:
                    s["iterations"][int(m2.group(1))] = d
                elif k.startswith("training_"):
                    model = k[len("training_"):]
                    s["models"][model] = d
                elif k in ("data_acquisition", "simulations", "training", "evaluation"):
                    s["phases"][k] = d

        summaries.append((label, s))

    if len(summaries) == 1:
        print_summary(summaries[0][0], summaries[0][1])
    elif len(summaries) > 1:
        for label, s in summaries:
            print_summary(label, s)
        print_comparison(summaries)


if __name__ == "__main__":
    main()
