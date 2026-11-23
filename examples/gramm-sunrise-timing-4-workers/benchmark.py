"""Time four stock Windows GRAMM workers on a 48-row AscendingBridge fixture."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
from statistics import median, pstdev
import struct
import subprocess
import time
import zipfile


INPUTS = ("ggeom.asc", "GRAMM.geb", "GRAMMin.dat", "IIN.dat", "landuse.asc",
          "Max_Proc.txt", "meteopgt.all")
ORDER = ("AB", "BA", "BA", "AB")
STABILITIES = (6,) * 20 + (4,) * 28
STAGGER_S = 0.300
ARM_DEADLINE_S = 270
EXPECTED_IDS = list(range(1, 69))


def sha(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def prepare(source, target):
    target.mkdir()
    for name in INPUTS:
        shutil.copyfile(source / name, target / name)
    gramm = target / "GRAMMin.dat"
    lines = gramm.read_bytes().splitlines()
    if len(lines) not in (5, 6) or lines[1].strip().lower() != b"y":
        raise ValueError("Expected the AscendingBridge GRAMMin.dat format")
    gramm.write_bytes(b"\r\n".join(lines[:5] + [b"48"]) + b"\r\n")
    iin = target / "IIN.dat"
    lines = iin.read_bytes().splitlines()
    if b"MODELLING TIME" not in lines[3]:
        raise ValueError("Expected the AscendingBridge IIN.dat format")
    lines[3] = b"MODELLING TIME : 1300"
    iin.write_bytes(b"\r\n".join(lines) + b"\r\n")
    (target / "Max_Proc.txt").write_bytes(b"1\r\n")
    meteo = target / "meteopgt.all"
    header = [b"10,1,15,", meteo.read_bytes().splitlines()[1]]
    rows = [f"2.3,1.50,{stability},2.0833333333".encode("ascii") for stability in STABILITIES]
    meteo.write_bytes(b"\r\n".join(header + rows) + b"\r\n")


def validate(folder):
    for ext in ("wnd", "scl"):
        if sorted(p.name for p in folder.glob(f"*.{ext}")) != [
                f"{i:05}.{ext}" for i in EXPECTED_IDS]:
            raise ValueError(f"Unexpected {ext} IDs")
    validation = []
    for i in EXPECTED_IDS:
        wind = folder / f"{i:05}.wnd"
        with wind.open("rb") as stream:
            header = struct.unpack("<iiiif", stream.read(20))
        if header != (-1, 26, 23, 20, 300.0) or wind.stat().st_size != 71780:
            raise ValueError(f"Invalid wind field {wind.name}")
        scalar = wind.with_suffix(".scl")
        # Stock sunrise copies intermediate archives under extra output IDs.
        original_id = i if i <= 48 else i - 48
        with zipfile.ZipFile(scalar) as archive:
            members = {info.filename: info.file_size for info in archive.infolist()}
            if len(archive.infolist()) != 3 or members != {
                    f"{original_id:05}.{ext}": 1216 for ext in ("ust", "obl", "scl")
            } or archive.testzip() is not None:
                raise ValueError(f"Invalid scalar field {scalar.name}")
        validation.append(dict(id=i, wnd_header=header, wnd_bytes=wind.stat().st_size,
                               members=members, crc_ok=True, wnd_sha256=sha(wind),
                               scl_sha256=sha(scalar)))
    rows = (folder / "meteopgt.all").read_text(encoding="ascii").splitlines()
    if rows[50:] != [f"23.150,{i}.1,6,0" for i in range(1, 21)]:
        raise ValueError("Unexpected sunrise output mapping")
    return validation


def exit_record(proc):
    code = proc.poll()
    if code is None:
        raise RuntimeError("Worker handle was not signaled")
    times = [wintypes.FILETIME() for _ in range(4)]
    # GetProcessTimes records process creation, exit, kernel CPU and user CPU
    # in 100-ns units, independent of the order in which we query completed handles.
    ok = ctypes.windll.kernel32.GetProcessTimes(
        wintypes.HANDLE(int(proc._handle)), *(ctypes.byref(v) for v in times))
    if not ok:
        raise ctypes.WinError()
    creation, end, kernel, user = [(v.dwHighDateTime << 32) | v.dwLowDateTime for v in times]
    return dict(code=code, os_start_100ns=creation, os_end_100ns=end,
                runtime_s=(end - creation) / 1e7, cpu_s=(kernel + user) / 1e7)


def run_arm(exe, folder, ranges):
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    workers = []
    start_mono = time.monotonic()
    deadline = start_mono + ARM_DEADLINE_S
    try:
        for first, last in ranges:
            if time.monotonic() >= deadline:
                raise TimeoutError("Shared arm deadline reached during launch")
            proc = subprocess.Popen([str(exe), str(folder), str(first), str(last)],
                                    cwd=folder, startupinfo=startup,
                                    creationflags=subprocess.CREATE_NEW_CONSOLE)
            workers.append(proc)
            if len(workers) < len(ranges):
                time.sleep(STAGGER_S)
        handles = (wintypes.HANDLE * len(workers))(*(int(p._handle) for p in workers))
        remaining_ms = max(0, int(1000 * (deadline - time.monotonic())))
        wait = ctypes.windll.kernel32.WaitForMultipleObjects
        wait.argtypes = (wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
                         wintypes.BOOL, wintypes.DWORD)
        wait.restype = wintypes.DWORD
        status = wait(len(workers), handles, True, remaining_ms)
        if status == 258:
            raise TimeoutError("Shared arm deadline reached; partial arm excluded")
        if status != 0:
            raise ctypes.WinError()
        rows = [exit_record(p) for p in workers]
    finally:
        for proc in workers:
            if proc.poll() is None:
                proc.kill()
        for proc in workers:
            proc.wait(timeout=max(0.01, start_mono + 290 - time.monotonic()))
    group_elapsed_s = time.monotonic() - start_mono
    if any(row["code"] != 0 for row in rows):
        raise RuntimeError(f"Worker failure: {rows}")
    start = min(row["os_start_100ns"] for row in rows)
    for row, bounds in zip(rows, ranges):
        row["range"] = bounds
        row["start_offset_s"] = (row["os_start_100ns"] - start) / 1e7
        row["finish_offset_s"] = (row["os_end_100ns"] - start) / 1e7
    elapsed = [row["runtime_s"] for row in rows]
    finish = [row["finish_offset_s"] for row in rows]
    if min(finish) <= max(row["start_offset_s"] for row in rows):
        raise RuntimeError("All four workers must overlap")
    return dict(workers=rows, worker_gap_s=max(elapsed) - min(elapsed),
                worker_sd_s=pstdev(elapsed), finish_gap_s=max(finish) - min(finish),
                makespan_s=max(finish), group_monotonic_s=group_elapsed_s,
                checks=validate(folder))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for key in ("exe", "fixture", "planner", "out"):
        cli.add_argument("--" + key, required=True, type=Path)
    args = cli.parse_args()
    exe, fixture, planner, out = (v.resolve() for v in (args.exe, args.fixture, args.planner, args.out))
    out.mkdir(parents=True, exist_ok=False)
    template = out / "inputs"
    prepare(fixture, template)
    weighted = json.loads(subprocess.check_output(["dotnet", str(planner), str(template)], text=True))
    if weighted != [[1, 6], [7, 12], [13, 18], [19, 48]]:
        raise ValueError(f"Unexpected actual GUI planner bounds: {weighted}")
    limits = {"A": [[1, 12], [13, 24], [25, 36], [37, 48]], "B": weighted}
    plan = dict(order=ORDER, warmup="AB", stagger_s=STAGGER_S, ranges=limits,
                original_count=48, sunrise_extra_count=20, max_proc_per_worker=1,
                per_arm_common_deadline_s=ARM_DEADLINE_S, deadline_clock="monotonic",
                stable_class_sequence=STABILITIES, speed_m_s=1.50, wind_direction_deg=23,
                modelling_time_s=1300, timeseries_header=1, logical_processors_pinned=False,
                primary="max minus min of four OS process lifetimes, seconds",
                secondary="last OS process exit minus first OS process start, seconds",
                results_summary="median and range, four measured trials per arm",
                created_utc=datetime.now(timezone.utc).isoformat(),
                windows=platform.platform(), logical_processors=os.cpu_count(),
                python=platform.python_version(),
                source_input_sha256={n: sha(fixture / n) for n in INPUTS},
                run_input_sha256={n: sha(template / n) for n in INPUTS},
                engine_sha256={p.name: sha(p) for p in [
                    exe, exe.with_suffix(".dll"), exe.with_suffix(".deps.json"),
                    exe.with_suffix(".runtimeconfig.json")]}, planner_dll_sha256=sha(planner))
    write_json(out / "plan.json", plan)
    runs = []
    for pair, order in enumerate(("AB", *ORDER)):
        for arm in order:
            folder = out / f"{pair:02}_{arm}"
            shutil.copytree(template, folder)
            result = dict(pair=pair, arm=arm, **run_arm(exe, folder, limits[arm]))
            runs.append(result)
            write_json(folder / "timing.json", result)
            print(f"{pair} {arm} gap={result['worker_gap_s']:.3f}s "
                  f"makespan={result['makespan_s']:.3f}s", flush=True)
    summary = {}
    for arm in limits:
        arm_runs = [r for r in runs if r["pair"] and r["arm"] == arm]
        summary[arm] = {}
        for key in ("worker_gap_s", "worker_sd_s", "finish_gap_s", "makespan_s", "group_monotonic_s"):
            values = [r[key] for r in arm_runs]
            summary[arm][key] = dict(median=median(values), min=min(values), max=max(values))
    write_json(out / "results.json", dict(plan=plan, runs=runs, summary=summary))


if __name__ == "__main__":
    main()
