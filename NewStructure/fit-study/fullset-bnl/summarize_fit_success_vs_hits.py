#!/usr/bin/env python3
"""Summarize MIP-fit acceptance as a function of triggered histogram statistics."""

import argparse
import csv
import math
from pathlib import Path
from statistics import median


DEFAULT_BINS = (0, 25, 50, 100, 200, 500, 1000, 2000, 5000, float("inf"))


def num(value):
    if value in (None, "", "?"):
        return None
    try:
        x = float(value)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def median_relative_error(rows, value_key, error_key):
    vals = []
    for row in rows:
        value = num(row.get(value_key))
        error = num(row.get(error_key))
        if value is None or error is None or value == 0:
            continue
        vals.append(abs(error / value))
    return median(vals) if vals else None


def label(lo, hi):
    if math.isinf(hi):
        return f">={lo:g}"
    return f"{lo:g}-{hi:g}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--source", default="adaptive",
                    help="Fit source prefix, e.g. adaptive, fixed10k, floor_1p0, floor_0p1.")
    args = ap.parse_args()

    with args.csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    source = args.source
    saved_key = f"{source}_fit_saved"
    chi_key = f"{source}_chi2_ndf"

    usable = [
        r for r in rows
        if num(r.get("mip_trigger_entries")) is not None
        and num(r.get(saved_key)) is not None
    ]

    print(f"Source: {source}")
    print(f"Rows with trigger statistics and source availability: {len(usable)}")
    print()
    print(
        "MIP triggers      rows   saved   save frac   med chi2/ndf   "
        "med dMPV/MPV   med dwL/wL   med dsig/sig"
    )
    for lo, hi in zip(DEFAULT_BINS[:-1], DEFAULT_BINS[1:]):
        subset = [
            r for r in usable
            if lo <= num(r["mip_trigger_entries"]) < hi
        ]
        if not subset:
            continue
        saved = [r for r in subset if num(r[saved_key]) == 1]
        chis = [num(r.get(chi_key)) for r in saved]
        chis = [x for x in chis if x is not None]
        chi = median(chis) if chis else None
        mpv_rel = median_relative_error(
            saved, f"{source}_mpv", f"{source}_mpv_err"
        )
        wl_rel = median_relative_error(
            saved, f"{source}_landau_width", f"{source}_landau_width_err"
        )
        sig_rel = median_relative_error(
            saved, f"{source}_gaussian_sigma", f"{source}_gaussian_sigma_err"
        )
        print(
            f"{label(lo,hi):14s} {len(subset):6d} {len(saved):7d} "
            f"{len(saved)/len(subset):10.3f} "
            f"{chi if chi is not None else float('nan'):14.3g} "
            f"{mpv_rel if mpv_rel is not None else float('nan'):13.3g} "
            f"{wl_rel if wl_rel is not None else float('nan'):12.3g} "
            f"{sig_rel if sig_rel is not None else float('nan'):14.3g}"
        )

    failed = [r for r in usable if num(r[saved_key]) == 0]
    saved = [r for r in usable if num(r[saved_key]) == 1]
    print()
    for name, group in (("saved", saved), ("failed", failed)):
        counts = sorted(num(r["mip_trigger_entries"]) for r in group)
        counts = [x for x in counts if x is not None]
        if counts:
            print(
                f"{name:6s}: n={len(counts)} "
                f"min={counts[0]:g} median={median(counts):g} max={counts[-1]:g}"
            )


if __name__ == "__main__":
    main()
