#!/usr/bin/env python3
"""Prepare pattern markers for the staged TB2026 raw-file set."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

RUN_RE = re.compile(r"^Run([0-9]+)\.h2g$")


def read_pairs(path: Path) -> list[tuple[int, int, int]]:
    pairs: list[tuple[int, int, int]] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 3:
            raise SystemExit(f"{path}:{lineno}: expected pedestal muon toa_set")
        pairs.append(tuple(map(int, fields)))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="raw")
    parser.add_argument("--pair-map", default="parameter-scan-pairs.tsv")
    parser.add_argument("--pair-dir", default="pairs")
    parser.add_argument("--expect-raw", type=int)
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    pair_dir = Path(args.pair_dir)
    if not raw_dir.is_dir():
        raise SystemExit(f"raw directory not found: {raw_dir}")

    runs: dict[int, Path] = {}
    for path in sorted(raw_dir.iterdir()):
        match = RUN_RE.match(path.name)
        if match:
            runs[int(match.group(1))] = path

    if args.expect_raw is not None and len(runs) != args.expect_raw:
        raise SystemExit(
            f"expected {args.expect_raw} staged Run*.h2g files, found {len(runs)}"
        )

    pair_dir.mkdir(parents=True, exist_ok=True)
    for old in pair_dir.glob("*.pair"):
        old.unlink()

    complete: list[tuple[int, int, int]] = []
    covered: set[int] = set()
    for ped, run, toa in read_pairs(Path(args.pair_map)):
        if ped not in runs or run not in runs:
            continue
        marker = pair_dir / f"ped{ped}_run{run}_toa{toa}.pair"
        marker.write_text(
            f"pedestal={ped}\nmuon={run}\ntoa_offset_set={toa}\n",
            encoding="utf-8",
        )
        complete.append((ped, run, toa))
        covered.update((ped, run))

    print(f"staged raw files: {len(runs)}")
    print(f"complete pedestal/muon pairs: {len(complete)}")
    for ped, run, toa in complete:
        print(f"  {ped} -> {run}  ToA set {toa}")

    uncovered = sorted(set(runs) - covered)
    if uncovered:
        print("staged runs not used by a complete calibration pair:")
        print("  " + " ".join(map(str, uncovered)))

    if not complete:
        print("no complete calibration pairs found", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
