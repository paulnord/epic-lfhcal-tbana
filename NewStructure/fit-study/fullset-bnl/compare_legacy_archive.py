#!/usr/bin/env python3
"""Audit changed fit cells across legacy, adaptive, and adjusted-grid outputs."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e1-bnl"))
from compare import calibration, fits  # noqa: E402


SET_NAMES = {
    "b1": "FullSetB_1",
    "b2": "FullSetB_2",
    "c2": "FullSetC_2",
    "c3": "FullSetC_3",
    "d1": "FullSetD_1",
    "e1": "FullSetE_1",
    "e2": "FullSetE_2",
    "e3": "FullSetE_3",
    "f1": "FullSetF_1",
    "f2": "FullSetF_2",
    "g1": "FullSetG_1",
    "g2": "FullSetG_2",
}


def files(directory: Path, set_name: str) -> tuple[Path, Path]:
    stem = f"rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{set_name}"
    return directory / f"{stem}_calib.txt", directory / f"{stem}_Hists.root"


def method_data(directory: Path, set_name: str, missing: list[str]):
    calib_path, hist_path = files(directory, set_name)

    absent = [str(path) for path in (calib_path, hist_path) if not path.is_file()]
    if absent:
        missing.extend(absent)
        return None

    return {
        "calibration": calibration(calib_path),
        "fits": fits(hist_path),
        "calib_path": str(calib_path),
        "hist_path": str(hist_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--adaptive-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    summary_path = args.candidate_root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    changed: dict[str, set[int]] = {}

    for code, cells in summary["totals"]["fits_lost"].items():
        changed.setdefault(code, set()).update(cells)

    for code, cells in summary["totals"]["fits_gained"].items():
        changed.setdefault(code, set()).update(cells)

    report = {
        "note": (
            "Historical legacy inputs differ upstream; legacy fit presence is "
            "descriptive rather than a controlled same-input comparison."
        ),
        "summary_source": str(summary_path),
        "cells": {},
    }

    missing: list[str] = []

    for code in sorted(changed):
        if code not in SET_NAMES:
            print(f"Unknown set code in summary: {code}", file=sys.stderr)
            return 2

        set_name = SET_NAMES[code]

        directories = {
            "legacy": args.legacy_root / f"fullset-{code}-repro" / "refine5",
            "adaptive": args.adaptive_root / f"adaptive-fullset-{code}-repro" / "refine5",
            "adjusted": args.candidate_root / code / "refine5",
        }

        data = {
            method: method_data(directory, set_name, missing)
            for method, directory in directories.items()
        }

        if any(values is None for values in data.values()):
            continue

        data = {method: values for method, values in data.items() if values is not None}

        for cell in sorted(changed[code]):
            key = f"{code}:{cell}"
            report["cells"][key] = {}

            for method, values in data.items():
                fit_map = values["fits"]
                calib_map = values["calibration"]

                report["cells"][key][method] = {
                    "fit_present": cell in fit_map,
                    "fit": fit_map.get(cell),
                    "calibration": calib_map.get(cell),
                    "calib_path": values["calib_path"],
                    "hist_path": values["hist_path"],
                }

            status = " ".join(
                f"{method}={'yes' if cell in data[method]['fits'] else 'no'}"
                for method in ("legacy", "adaptive", "adjusted")
            )
            print(f"{code} cell {cell}: {status}")

    report["missing_files"] = sorted(set(missing))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Saved audit: {args.out}")

    if missing:
        for path in sorted(set(missing)):
            print(f"MISSING {path}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
