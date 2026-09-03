#!/usr/bin/env python3
"""Build CompareWaveform two-column input lists from completed yawl products."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import re

RUN_RE = re.compile(r"Run_([0-9]+)")


def run_from_path(value: str) -> int:
    match = RUN_RE.search(Path(value).name)
    if not match:
        raise SystemExit(f"cannot extract run number from {value}")
    return int(match.group(1))


def run_info(path: Path) -> dict[int, dict[str, int]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("Run Number,"))
    except StopIteration as exc:
        raise SystemExit(f"run database header not found in {path}") from exc

    result: dict[int, dict[str, int]] = {}
    reader = csv.DictReader(lines[start:])
    for row in reader:
        try:
            run = int(row["Run Number"])
            result[run] = {
                "RF": int(row["RF"]),
                "CF": int(row["CF"]),
                "CC": int(row["CC"]),
                "CFComp": int(row["CFComp"]),
            }
        except (TypeError, ValueError, KeyError):
            continue
    return result


def write_list(path: Path, runs: list[int], calib: dict[int, str], hist: dict[int, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{calib[run]} {hist[run]}\n" for run in runs),
        encoding="utf-8",
    )
    if not runs:
        raise SystemExit(f"comparison subset would be empty: {path}")
    print(f"{path}: {len(runs)} runs")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rundb", required=True)
    parser.add_argument("--calib", nargs="+", required=True)
    parser.add_argument("--hist", nargs="+", required=True)
    parser.add_argument("--all", dest="all_path", required=True)
    parser.add_argument("--rf", required=True)
    parser.add_argument("--cf", required=True)
    parser.add_argument("--cfcomp", required=True)
    parser.add_argument("--cc", required=True)
    args = parser.parse_args()

    calib = {run_from_path(path): path for path in args.calib}
    hist = {run_from_path(path): path for path in args.hist}
    if set(calib) != set(hist):
        raise SystemExit(
            f"calibrated/waveform run sets differ: calib={sorted(calib)} hist={sorted(hist)}"
        )

    info = run_info(Path(args.rundb))
    runs = sorted(calib)
    missing = [run for run in runs if run not in info]
    if missing:
        raise SystemExit(f"runs missing from run database: {missing}")

    def subset(predicate):
        return [run for run in runs if predicate(info[run])]

    write_list(Path(args.all_path), runs, calib, hist)
    write_list(
        Path(args.rf),
        subset(lambda x: x["CF"] == 7 and x["CC"] == 5 and x["CFComp"] == 1),
        calib,
        hist,
    )
    write_list(
        Path(args.cf),
        subset(lambda x: x["RF"] == 9 and x["CC"] == 5 and x["CFComp"] == 1),
        calib,
        hist,
    )
    write_list(
        Path(args.cfcomp),
        subset(lambda x: x["RF"] == 9 and x["CF"] == 5 and x["CC"] == 5),
        calib,
        hist,
    )
    write_list(
        Path(args.cc),
        subset(lambda x: x["RF"] == 9 and x["CF"] == 7 and x["CFComp"] == 1),
        calib,
        hist,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
