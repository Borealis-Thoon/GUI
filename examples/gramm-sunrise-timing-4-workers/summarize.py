"""Recalculate four-worker trial summaries from the raw Windows process times."""
import argparse
import csv
import json
import math
from pathlib import Path
from statistics import median, pstdev


def write_csv(path, rows):
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("run_directory", type=Path)
    cli.add_argument("output_directory", type=Path)
    args = cli.parse_args()
    data = json.loads((args.run_directory / "results.json").read_text(encoding="utf-8"))
    out = args.output_directory
    out.mkdir(parents=True, exist_ok=False)
    trials, workers = [], []
    plan = data["plan"]
    for run in data["runs"]:
        if len(run["workers"]) != 4 or run["group_monotonic_s"] >= plan["per_arm_common_deadline_s"]:
            raise ValueError("Invalid worker count or common deadline exceeded")
        if any(w["code"] != 0 for w in run["workers"]):
            raise ValueError("Worker failure")
        if len(run["checks"]) != plan["original_count"] + plan["sunrise_extra_count"]:
            raise ValueError("Unexpected output count")
        arm, pair = run["arm"], run["pair"]
        starts = [w["os_start_100ns"] for w in run["workers"]]
        ends = [w["os_end_100ns"] for w in run["workers"]]
        durations = [(end - start) / 1e7 for start, end in zip(starts, ends)]
        if max(starts) >= min(ends):
            raise ValueError("Four-way overlap was absent")
        stats = dict(worker_gap_s=max(durations)-min(durations), worker_sd_s=pstdev(durations),
                     finish_gap_s=(max(ends)-min(ends))/1e7, makespan_s=(max(ends)-min(starts))/1e7)
        if not all(math.isclose(v, run[k], abs_tol=1e-8) for k, v in stats.items()):
            raise ValueError("Recalculated timing does not match the raw report")
        trials.append(dict(pair=pair, arm=arm, warmup=pair == 0, **stats,
                           four_worker_overlap_s=(min(ends)-max(starts))/1e7,
                           group_monotonic_s=run["group_monotonic_s"], originals=plan["original_count"],
                           sunrise_extras=plan["sunrise_extra_count"]))
        for i, worker in enumerate(run["workers"]):
            workers.append(dict(pair=pair, arm=arm, warmup=pair == 0, worker=i+1,
                                first=worker["range"][0], last=worker["range"][1],
                                start_100ns=starts[i], exit_100ns=ends[i],
                                start_offset_s=(starts[i]-min(starts))/1e7,
                                finish_offset_s=(ends[i]-min(starts))/1e7,
                                runtime_s=durations[i], cpu_s=worker["cpu_s"], exit_code=worker["code"]))
    if [(r["pair"], r["arm"]) for r in trials] != [
        (number, arm) for number, order in enumerate((plan["warmup"], *plan["order"])) for arm in order
    ]:
        raise ValueError("Run sequence differs from the declared plan")
    summaries = {}
    for metric in ("worker_gap_s", "worker_sd_s", "finish_gap_s", "makespan_s"):
        arms = {}
        for arm in "AB":
            values = [row[metric] for row in trials if row["pair"] > 0 and row["arm"] == arm]
            arms[arm] = dict(median=median(values), min=min(values), max=max(values))
        a, b = arms["A"]["median"], arms["B"]["median"]
        delta = []
        for n in range(1, len(plan["order"]) + 1):
            pair = {r["arm"]: r[metric] for r in trials if r["pair"] == n}
            delta.append(pair["A"]-pair["B"])
        summaries[metric] = dict(arms=arms, median_difference_s=a-b,
                                 relative_reduction_in_medians_pct=100*(a-b)/a,
                                 paired_A_minus_B_s=delta, pairs_lower_B=sum(v > 0 for v in delta))
    write_csv(out / "trials.csv", trials)
    write_csv(out / "worker_times.csv", workers)
    (out / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
