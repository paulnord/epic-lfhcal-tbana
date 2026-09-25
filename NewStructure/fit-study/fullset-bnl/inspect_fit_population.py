#!/usr/bin/env python3
"""Inspect Langau fit-parameter populations and changed cells across a full-set replay."""

import argparse
import csv
import json
import math
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e1-bnl"))
from compare import fits  # noqa: E402


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


def calibration(path: Path) -> dict[int, dict[str, float | int]]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 18 or not fields[0].isdigit():
            continue
        cell = int(fields[0])
        result[cell] = {
            "pedestal_mean_h": float(fields[5]),
            "pedestal_sigma_h": float(fields[6]),
            "mip_scale_h": float(fields[9]),
            "mip_fwhm_h": float(fields[10]),
            "bad_channel": int(fields[17]),
        }
    if not result:
        raise ValueError(f"no calibration records found in {path}")
    return result


def files(directory: Path, set_name: str) -> tuple[Path, Path]:
    stem = f"rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{set_name}"
    return directory / f"{stem}_calib.txt", directory / f"{stem}_Hists.root"


def metric_row(code: str, cell: int, method: str, fit: dict[str, float],
               calib: dict[str, float | int], kind: str) -> dict[str, object]:
    width = fit["landau_width"]
    sigma = fit["gaussian_sigma"]
    mpv = fit["mpv"]
    ped_sigma = float(calib["pedestal_sigma_h"])
    return {
        "set": code,
        "cell": cell,
        "kind": kind,
        "method": method,
        "landau_width": width,
        "mpv": mpv,
        "gaussian_sigma": sigma,
        "sigma_over_landau": sigma / width if width != 0 else None,
        "landau_over_mpv": width / mpv if mpv != 0 else None,
        "sigma_over_pedestal": sigma / ped_sigma if ped_sigma > 0 else None,
        "chi2_ndf": fit["chi2_ndf"],
        "pedestal_sigma_h": ped_sigma,
        "mip_scale_h": float(calib["mip_scale_h"]),
        "mip_fwhm_h": float(calib["mip_fwhm_h"]),
        "bad_channel": int(calib["bad_channel"]),
    }


def percentile(values: list[float], x: float) -> float | None:
    if not values or not math.isfinite(x):
        return None
    below = sum(v < x for v in values)
    equal = sum(v == x for v in values)
    return 100.0 * (below + 0.5 * equal) / len(values)


def quantile(values: list[float], q: float) -> float | None:
    vals = sorted(v for v in values if math.isfinite(v))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = q * (len(vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return vals[lo]
    frac = pos - lo
    return vals[lo] * (1.0 - frac) + vals[hi] * frac


def summarize(values: list[float]) -> dict[str, float | int | None]:
    vals = [v for v in values if v is not None and math.isfinite(v)]
    return {
        "count": len(vals),
        "min": min(vals) if vals else None,
        "p01": quantile(vals, 0.01),
        "p05": quantile(vals, 0.05),
        "p25": quantile(vals, 0.25),
        "median": quantile(vals, 0.50),
        "p75": quantile(vals, 0.75),
        "p95": quantile(vals, 0.95),
        "p99": quantile(vals, 0.99),
        "max": max(vals) if vals else None,
    }


def fmt(value: object, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adaptive-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--previous-summary", type=Path, required=True,
                        help="Summary from the moving-grid replay used to identify rescued losses.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    current_summary = json.loads(
        (args.candidate_root / "summary.json").read_text(encoding="utf-8")
    )
    previous_summary = json.loads(args.previous_summary.read_text(encoding="utf-8"))

    current_lost = {
        code: set(cells)
        for code, cells in current_summary["totals"].get("fits_lost", {}).items()
    }
    previous_lost = {
        code: set(cells)
        for code, cells in previous_summary["totals"].get("fits_lost", {}).items()
    }
    current_gained = {
        code: set(cells)
        for code, cells in current_summary["totals"].get("fits_gained", {}).items()
    }

    targets: dict[tuple[str, int], str] = {}
    for code, cells in current_gained.items():
        for cell in cells:
            targets[(code, cell)] = "gained_vs_adaptive"
    for code, cells in previous_lost.items():
        for cell in cells - current_lost.get(code, set()):
            targets[(code, cell)] = "rescued_moving_grid_loss"

    candidate_rows = []
    target_rows = []
    target_report = {}
    missing = []

    for code, set_name in SET_NAMES.items():
        candidate_dir = args.candidate_root / code / "refine5"
        adaptive_dir = args.adaptive_root / f"adaptive-fullset-{code}-repro" / "refine5"

        cand_calib_path, cand_hist_path = files(candidate_dir, set_name)
        adapt_calib_path, adapt_hist_path = files(adaptive_dir, set_name)

        for path in (cand_calib_path, cand_hist_path, adapt_calib_path, adapt_hist_path):
            if not path.is_file():
                missing.append(str(path))

        if any(not path.is_file() for path in (
            cand_calib_path, cand_hist_path, adapt_calib_path, adapt_hist_path
        )):
            continue

        cand_calib = calibration(cand_calib_path)
        adapt_calib = calibration(adapt_calib_path)
        cand_fits = fits(cand_hist_path)
        adapt_fits = fits(adapt_hist_path)

        for cell, fit in cand_fits.items():
            if cell not in cand_calib:
                continue
            candidate_rows.append(
                metric_row(code, cell, "candidate", fit, cand_calib[cell], "population")
            )

        for (target_code, cell), kind in sorted(targets.items()):
            if target_code != code:
                continue
            key = f"{code}:{cell}"
            entry = {"kind": kind, "candidate": None, "adaptive": None}

            if cell in cand_fits and cell in cand_calib:
                row = metric_row(code, cell, "candidate", cand_fits[cell], cand_calib[cell], kind)
                target_rows.append(row)
                entry["candidate"] = row

            if cell in adapt_fits and cell in adapt_calib:
                row = metric_row(code, cell, "adaptive", adapt_fits[cell], adapt_calib[cell], kind)
                target_rows.append(row)
                entry["adaptive"] = row

            target_report[key] = entry

    metric_names = (
        "landau_width",
        "gaussian_sigma",
        "sigma_over_landau",
        "landau_over_mpv",
        "sigma_over_pedestal",
        "chi2_ndf",
    )
    population_values = {
        metric: [
            float(row[metric])
            for row in candidate_rows
            if row[metric] is not None and math.isfinite(float(row[metric]))
        ]
        for metric in metric_names
    }
    population_summary = {
        metric: summarize(values)
        for metric, values in population_values.items()
    }

    for row in target_rows:
        if row["method"] != "candidate":
            continue
        row["population_percentiles"] = {
            metric: percentile(population_values[metric], float(row[metric]))
            if row[metric] is not None else None
            for metric in metric_names
        }

    report = {
        "note": (
            "Candidate population is the fixed-10000-point rescue replay. "
            "Targets include current gains versus adaptive plus fits lost by the "
            "previous moving-grid replay that are no longer lost."
        ),
        "candidate_fit_count": len(candidate_rows),
        "targets": target_report,
        "population": population_summary,
        "missing_files": sorted(set(missing)),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    csv_path = args.out.with_suffix(".csv")
    csv_fields = [
        "set", "cell", "kind", "method",
        "landau_width", "mpv", "gaussian_sigma",
        "sigma_over_landau", "landau_over_mpv", "sigma_over_pedestal",
        "chi2_ndf", "pedestal_sigma_h", "mip_scale_h", "mip_fwhm_h", "bad_channel",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(target_rows)

    print(f"Candidate population: {len(candidate_rows)} saved fits")
    print()
    print("Population percentiles:")
    print("metric                         p05        median       p95        p99")
    for metric in metric_names:
        stats = population_summary[metric]
        print(
            f"{metric:28s} "
            f"{fmt(stats['p05'], 4):>10s} "
            f"{fmt(stats['median'], 4):>12s} "
            f"{fmt(stats['p95'], 4):>10s} "
            f"{fmt(stats['p99'], 4):>10s}"
        )

    print()
    print("Changed/rescued cells (candidate fit):")
    print(
        "set cell   kind                       wL      sigma   sig/wL  "
        "wL/MPV sig/ped chi2/ndf  BC"
    )
    for key, entry in sorted(target_report.items()):
        row = entry["candidate"]
        if not row:
            code, cell = key.split(":")
            print(f"{code:3s} {cell:>4s}   {entry['kind']:<26s} MISSING")
            continue
        print(
            f"{row['set']:3s} {row['cell']:4d}   {row['kind']:<26s} "
            f"{fmt(row['landau_width']):>7s} "
            f"{fmt(row['gaussian_sigma']):>7s} "
            f"{fmt(row['sigma_over_landau']):>7s} "
            f"{fmt(row['landau_over_mpv']):>7s} "
            f"{fmt(row['sigma_over_pedestal']):>7s} "
            f"{fmt(row['chi2_ndf']):>8s} "
            f"{row['bad_channel']:3d}"
        )

    print()
    print(f"Saved JSON: {args.out}")
    print(f"Saved CSV:  {csv_path}")

    if missing:
        for path in sorted(set(missing)):
            print(f"MISSING {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
