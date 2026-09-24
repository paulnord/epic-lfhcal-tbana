#!/usr/bin/env python3
"""Combine per-set refine5 comparisons into one reviewable JSON document."""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("comparisons", nargs="+", type=Path)
    args = parser.parse_args()
    sets = {}
    for path in args.comparisons:
        code = path.parent.name
        sets[code] = json.loads(path.read_text(encoding="utf-8"))
    report = {
        "note": "Numerical comparison only; no scientific acceptance is inferred.",
        "sets": sets,
        "totals": {
            "baseline_fits": sum(item["baseline_fit_count"] for item in sets.values()),
            "candidate_fits": sum(item["candidate_fit_count"] for item in sets.values()),
            "fits_lost": {code: item["fits_lost"] for code, item in sets.items() if item["fits_lost"]},
            "fits_gained": {code: item["fits_gained"] for code, item in sets.items() if item["fits_gained"]},
        },
    }
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved summary: {args.out}")
    print(f"Saved HG fits: {report['totals']['baseline_fits']} -> {report['totals']['candidate_fits']}")
    print(f"Fits lost: {report['totals']['fits_lost']}")
    print(f"Fits gained: {report['totals']['fits_gained']}")


if __name__ == "__main__":
    main()
