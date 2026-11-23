"""Compare all WND components and uncompressed SCL members after the timing runs."""
import argparse
import csv
from itertools import combinations
import json
from pathlib import Path
import struct
import zipfile


def compare_field(left, right, field_id):
    wind = f"{field_id:05}.wnd"
    a, b = [(folder / wind).read_bytes() for folder in (left, right)]
    for data in (a, b):
        if len(data) != 71780 or struct.unpack_from("<iiiif", data) != (-1, 26, 23, 20, 300.0):
            raise ValueError(f"Unexpected WND format: {wind}")
    unequal = max_raw = 0
    if a != b:
        x = struct.unpack_from("<35880h", a, 20)
        y = struct.unpack_from("<35880h", b, 20)
        deltas = [abs(m - n) for m, n in zip(x, y)]
        unequal, max_raw = sum(d != 0 for d in deltas), max(deltas)

    scalar = f"{field_id:05}.scl"
    changed = []
    with zipfile.ZipFile(left / scalar) as a, zipfile.ZipFile(right / scalar) as b:
        if sorted(a.namelist()) != sorted(b.namelist()):
            raise ValueError(f"Different scalar member sets: {scalar}")
        for name in sorted(a.namelist()):
            if a.read(name) != b.read(name):
                changed.append(Path(name).suffix[1:])
    return unequal, max_raw / 100, " ".join(changed)


def write_table(path, records):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("run_directory", type=Path)
    cli.add_argument("output_directory", type=Path)
    args = cli.parse_args()
    folder, out = args.run_directory, args.output_directory
    out.mkdir(parents=True, exist_ok=False)
    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    original = data["plan"]["original_count"]
    count = original + data["plan"]["sunrise_extra_count"]
    measured = [r for r in data["runs"] if r["pair"] > 0]
    pairs = sorted({r["pair"] for r in measured})
    ids = list(range(1, count + 1))
    for run in measured:
        if [r["id"] for r in run["checks"]] != ids:
            raise ValueError("Incomplete set of validated field IDs")
    comparisons = [("paired_AB", f"{n:02}_A", f"{n:02}_B") for n in pairs]
    for arm in "AB":
        for x, y in combinations(pairs, 2):
            comparisons.append((f"repeat_{arm}", f"{x:02}_{arm}", f"{y:02}_{arm}"))

    records = []
    for scope, left, right in comparisons:
        for field_id in ids:
            unequal, maximum, members = compare_field(folder / left, folder / right, field_id)
            records.append(dict(scope=scope, left=left, right=right, id=field_id,
                                original=field_id <= original, unequal_components=unequal,
                                max_abs_delta_m_s=maximum, changed_scalar_members=members))
    write_table(out / "field_comparisons.csv", records)
    per_id = []
    summary = {}
    for scope in ("paired_AB", "repeat_A", "repeat_B"):
        rows = [r for r in records if r["scope"] == scope]
        for field_id in ids:
            samples = [r for r in rows if r["id"] == field_id]
            per_id.append(dict(scope=scope, id=field_id, comparisons=len(samples),
                               wind_different_comparisons=sum(r["unequal_components"] > 0 for r in samples),
                               min_unequal_components=min(r["unequal_components"] for r in samples),
                               max_unequal_components=max(r["unequal_components"] for r in samples),
                               min_of_max_abs_delta_m_s=min(r["max_abs_delta_m_s"] for r in samples),
                               max_abs_delta_m_s=max(r["max_abs_delta_m_s"] for r in samples),
                               scalar_different_comparisons=sum(bool(r["changed_scalar_members"]) for r in samples)))
        summary[scope] = {}
        for subset, group in (("original", True), ("sunrise", False)):
            selected = [r for r in rows if r["original"] == group]
            wind_ids = sorted({r["id"] for r in selected if r["unequal_components"]})
            scalar_ids = sorted({r["id"] for r in selected if r["changed_scalar_members"]})
            summary[scope][subset] = dict(wind_different_ids=wind_ids, scalar_different_ids=scalar_ids,
                                         wind_different_count=len(wind_ids), scalar_different_count=len(scalar_ids),
                                         max_abs_delta_m_s=max(r["max_abs_delta_m_s"] for r in selected))
    write_table(out / "field_summary_by_id.csv", per_id)
    (out / "field_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for scope, subsets in summary.items():
        print(scope, [(key, s["wind_different_count"], s["max_abs_delta_m_s"])
                      for key, s in subsets.items()])


if __name__ == "__main__":
    main()
