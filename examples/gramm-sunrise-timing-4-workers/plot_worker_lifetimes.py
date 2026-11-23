"""Render the four-worker AscendingBridge sunrise timing figure.

Usage: python plot_worker_lifetimes.py EXAMPLE/fixed gramm_worker_lifetimes.png
Requires Matplotlib. Inputs are the original benchmark output files.
"""

import argparse
import csv
import json
from math import ceil, isfinite
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


ARMS = (
    ("A", "Equal-count ranges", "#9C431F", "o"),
    ("B", "Weighted ranges", "#0C636D", "D"),
)
WORKERS = (1, 2, 3, 4)
PAIRS = {1, 2, 3, 4}


def read_benchmark(results_dir):
    with (results_dir / "worker_times.csv").open(encoding="utf-8-sig", newline="") as source:
        worker_rows = [
            row for row in csv.DictReader(source) if row["warmup"] == "False"
        ]
    with (results_dir / "trials.csv").open(encoding="utf-8-sig", newline="") as source:
        trials = [row for row in csv.DictReader(source) if row["warmup"] == "False"]

    expected_trials = {(arm, pair) for arm, *_ in ARMS for pair in PAIRS}
    trial_keys = {(row["arm"], int(row["pair"])) for row in trials}
    if trial_keys != expected_trials or len(trials) != len(expected_trials):
        raise ValueError("Expected four measured trials for each range policy.")
    if {(row["originals"], row["sunrise_extras"]) for row in trials} != {("48", "20")}:
        raise ValueError("Expected 48 original situations and 20 sunrise additions.")

    samples = {}
    assigned_ranges = {}
    for row in worker_rows:
        arm, worker, pair = row["arm"], int(row["worker"]), int(row["pair"])
        key = (arm, worker, pair)
        if key in samples or row["exit_code"] != "0":
            raise ValueError(f"Duplicate or unsuccessful worker record {key}.")
        samples[key] = float(row["runtime_s"])
        if not isfinite(samples[key]) or samples[key] <= 0:
            raise ValueError(f"Invalid lifetime for {key}.")
        assigned_ranges.setdefault((arm, worker), set()).add(
            (int(row["first"]), int(row["last"]))
        )
    expected_workers = {(arm, worker, pair) for arm, pair in expected_trials for worker in WORKERS}
    if samples.keys() != expected_workers:
        raise ValueError("Expected one lifetime for each measured trial and worker.")

    if assigned_ranges["B", 4] != {(19, 48)}:
        raise ValueError("Expected weighted worker 4 to receive original situations 19–48.")
    counts = {}
    for key, ranges in assigned_ranges.items():
        if len(ranges) != 1:
            raise ValueError(f"Worker range varies across runs for {key}.")
        (first, last), = ranges
        counts[key] = last - first + 1

    manifest = json.loads((results_dir / "manifest.json").read_text(encoding="utf-8-sig"))
    commit = manifest["engine_source_commit"]
    if commit != "58fcb6f4f480cf688882e71f453eee93a989b560":
        raise ValueError("Expected final corrected GRAMM engine 58fcb6f.")
    if manifest["benchmark_inputs_sha256"]["meteopgt.all"] != "c87a8ffe27b896e94c3348861ccb69a7e915cab7f890136b49f820ce8fdcc8fe":
        raise ValueError("Expected the fixture with 20 class-6 rows followed by 28 class-4 rows.")

    grouped_samples = {
        (arm, worker): [samples[arm, worker, pair] for pair in sorted(PAIRS)]
        for arm, *_ in ARMS for worker in WORKERS
    }
    return grouped_samples, counts, commit[:7]


def render(samples, counts, engine, output):
    ink = "#172938"
    secondary = "#43596A"
    grid = "#DFE7ED"
    with plt.rc_context({"font.family": "DejaVu Sans", "text.color": ink}):
        fig = plt.figure(figsize=(9.4, 5.05), facecolor="white")
        ax = fig.add_axes((0.174, 0.248, 0.775, 0.492))
        fig.text(0.043, 0.930, "Weighted ranges bring worker lifetimes closer",
                 fontsize=22, weight="bold", va="center")
        fig.text(0.044, 0.862,
                 f"AscendingBridge sunrise case  ·  GRAMM {engine}  ·  "
                 "48 original situations + 20 sunrise additions",
                 fontsize=11.4, color=secondary, va="center")
        legend_handles = [
            Line2D([], [], color=color, marker=marker, linestyle="none",
                   markersize=7.5, label=label)
            for _, label, color, marker in ARMS
        ]
        legend_handles.append(Line2D([], [], color=secondary, marker="|", linestyle="none",
                                    markersize=8, label="Individual runs"))
        fig.legend(handles=legend_handles, loc="center left", bbox_to_anchor=(0.032, 0.790),
                   frameon=False, ncol=3, fontsize=11.5, handletextpad=0.32,
                   columnspacing=1.45, labelcolor=ink)

        max_seconds = 10 * ceil(max(max(runs) for runs in samples.values()) / 10)
        ax.set(xlim=(0, max_seconds), ylim=(-0.48, 3.57), axisbelow=True)
        ax.set_xticks(range(0, max_seconds + 1, 10))
        ax.set_yticks([])
        ax.grid(axis="x", color=grid, linewidth=0.8)
        ax.tick_params(axis="x", length=0, pad=8, labelsize=11.5, colors=secondary)
        ax.set_xlabel("Process lifetime (s), including startup", fontsize=12,
                      labelpad=9, color=ink)
        for spine in ax.spines.values():
            spine.set_visible(False)

        for worker in WORKERS:
            y = 4 - worker
            medians = [median(samples[arm, worker]) for arm, *_ in ARMS]
            before, after = (counts[arm, worker] for arm, *_ in ARMS)
            row_labels = ax.get_yaxis_transform()
            ax.text(-0.021, y + 0.13, f"Worker {worker}", transform=row_labels,
                    ha="right", va="center", fontsize=12.6, color=ink)
            ax.text(-0.021, y - 0.18, f"{before} → {after} originals", transform=row_labels,
                    ha="right", va="center", fontsize=9.5, color=secondary)
            ax.hlines(y, *sorted(medians), color="#A4B4C0", linewidth=2.1)
            for (arm, _, color, marker), value in zip(ARMS, medians, strict=True):
                runs = samples[arm, worker]
                ax.vlines(runs, y - 0.27, y - 0.11, color=color, linewidth=0.95, alpha=0.65)
                ax.scatter(value, y, marker=marker, s=79, color=color, edgecolors="white",
                           linewidths=0.9, zorder=4)
                ax.annotate(f"{value:.2f}", (value, y), xytext=(0, 8.5),
                            textcoords="offset points", ha="center", va="bottom",
                            color=color, fontsize=10.7, weight="bold")

        fig.add_artist(Line2D([0.044, 0.949], [0.118, 0.118], transform=fig.transFigure,
                              color=grid, linewidth=0.8))
        fig.text(0.044, 0.087, "Large markers show medians of four runs per layout.",
                 fontsize=10.5, color=secondary, va="center")
        fig.text(0.044, 0.047, "With weighting, worker 4 takes 28 short class-4 situations "
                 "and 2 long class-6 situations.", fontsize=10.5, color=secondary, va="center")
        fig.savefig(output, dpi=200, facecolor="white",
                    metadata={"Title": "Weighted ranges bring worker lifetimes closer",
                              "Description": f"AscendingBridge sunrise benchmark, GRAMM {engine}."})
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixed_results", type=Path, help="fixed benchmark output directory")
    parser.add_argument("output", type=Path, help="output PNG file")
    args = parser.parse_args()
    samples, counts, engine = read_benchmark(args.fixed_results)
    render(samples, counts, engine, args.output)


if __name__ == "__main__":
    main()
