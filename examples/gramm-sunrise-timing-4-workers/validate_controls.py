"""Run matched controls for the fixed steady-state engine after the four-worker suite."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import benchmark as bench
from compare_wind import compare_field, write_table


def identity(folder, names):
    return {n: bench.sha(folder / n) for n in names}


def check_inputs(stock, candidate, exe):
    reference = json.loads((stock / "plan.json").read_text(encoding="utf-8"))
    tested = json.loads((candidate / "plan.json").read_text(encoding="utf-8"))
    for key in ("run_input_sha256", "source_input_sha256", "planner_dll_sha256", "ranges",
                "order", "stagger_s", "per_arm_common_deadline_s"):
        if reference[key] != tested[key]:
            raise ValueError(f"Incompatible runs: {key}")
    if identity(candidate / "inputs", bench.INPUTS) != reference["run_input_sha256"]:
        raise ValueError("Candidate input files changed")
    if exe.name not in tested["engine_sha256"] or identity(exe.parent, tested["engine_sha256"]) != tested["engine_sha256"]:
        raise ValueError("Candidate engine identity changed")
    return tested


def one_worker(exe, folder, first, last, ids):
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    begin = time.monotonic()
    with subprocess.Popen([str(exe), str(folder), str(first), str(last)], cwd=folder,
                          startupinfo=startup, creationflags=subprocess.CREATE_NEW_CONSOLE) as proc:
        try:
            code = proc.wait(timeout=max(0, begin + bench.ARM_DEADLINE_S - time.monotonic()))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=15)
    elapsed = time.monotonic() - begin
    if code or elapsed >= bench.ARM_DEADLINE_S:
        raise RuntimeError(f"Control failed: {first}..{last}, code={code}, seconds={elapsed}")
    for ext in ("wnd", "scl"):
        if sorted(p.name for p in folder.glob(f"*.{ext}")) != [f"{i:05}.{ext}" for i in ids]:
            raise ValueError(f"Unexpected {ext} IDs for {first}..{last}")
    if ids == bench.EXPECTED_IDS:
        bench.validate(folder)
    return dict(range=[first, last], code=code, monotonic_s=elapsed, output_ids=ids)


def compare(rows, scope, left, right, ids):
    for i in ids:
        unequal, maximum, members = compare_field(left, right, i)
        rows.append(dict(scope=scope, left=left.name, right=right.name, id=i,
                         unequal_wind_components=unequal, max_abs_delta_m_s=maximum,
                         changed_scalar_members=members))


def measured_folders(run):
    data = json.loads((run / "results.json").read_text(encoding="utf-8"))
    return [run / f"{r['pair']:02}_{r['arm']}" for r in data["runs"] if r["pair"]]


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("scope", choices=("isolated", "single", "multi"))
    for key in ("stock-run", "candidate-run", "exe", "out"):
        cli.add_argument("--" + key, type=Path, required=True)
    args = cli.parse_args()
    stock, candidate, exe, out = [p.resolve() for p in (args.stock_run, args.candidate_run, args.exe, args.out)]
    plan = check_inputs(stock, candidate, exe)
    out.mkdir(parents=True, exist_ok=False)
    template = candidate / "inputs"
    tested = measured_folders(candidate)
    rows, runs = [], []
    if args.scope == "isolated":
        for i in (1, 7, 19, 21):
            folder = out / f"isolated_{i:02}"
            shutil.copytree(template, folder)
            if i > 1:
                # A stock process starting above ID 1 waits for this terrain/radiation cache.
                # The candidate's isolated case 1 creates it in the matching pristine fixture.
                cache = out / "isolated_01" / "albeq.dat"
                cache_hash = bench.sha(cache)
                if not all(bench.sha(f / "albeq.dat") == cache_hash for f in tested):
                    raise ValueError("Candidate geometry cache varies across identical inputs")
                shutil.copyfile(cache, folder / "albeq.dat")
            ids = [i, 48+i] if i <= 20 else [i]
            runs.append(one_worker(exe, folder, i, i, ids))
            for reference in tested:
                compare(rows, "isolated_vs_candidate_measured", folder, reference, ids)
            if i == 1:
                for reference in measured_folders(stock):
                    compare(rows, "isolated_case1_vs_stock_measured", folder, reference, ids)
                for a in measured_folders(stock):
                    for b in tested:
                        compare(rows, "stock_case1_vs_candidate_measured", a, b, ids)
    elif args.scope == "single":
        folder = out / "single_1_to_48"
        shutil.copytree(template, folder)
        runs.append(one_worker(exe, folder, 1, 48, bench.EXPECTED_IDS))
        for reference in tested:
            compare(rows, "one_process_vs_candidate_measured", folder, reference, bench.EXPECTED_IDS)
    else:
        for arm in "AB":
            folder = out / f"two_threads_{arm}"
            shutil.copytree(template, folder)
            (folder / "Max_Proc.txt").write_bytes(b"2\r\n")
            runs.append(bench.run_arm(exe, folder, plan["ranges"][arm]))
            for reference in tested:
                if reference.name.endswith(f"_{arm}"):
                    compare(rows, "two_threads_vs_one_thread_same_split", folder, reference, bench.EXPECTED_IDS)
        compare(rows, "two_threads_A_vs_B", out / "two_threads_A", out / "two_threads_B", bench.EXPECTED_IDS)
    write_table(out / "comparisons.csv", rows)
    summary = {}
    for group in sorted({r["scope"] for r in rows}):
        subset = [r for r in rows if r["scope"] == group]
        summary[group] = dict(field_comparisons=len(subset), max_abs_delta_m_s=max(r["max_abs_delta_m_s"] for r in subset),
                              differing_wind_ids=sorted({r["id"] for r in subset if r["unequal_wind_components"]}),
                              differing_scalar_ids=sorted({r["id"] for r in subset if r["changed_scalar_members"]}))
    bench.write_json(out / "controls.json", dict(scope=args.scope, summary=summary, runs=runs))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
