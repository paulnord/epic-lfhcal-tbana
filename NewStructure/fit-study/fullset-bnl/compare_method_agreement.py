#!/usr/bin/env python3
"""Compare adaptive and fixed-grid Langau fits across all common saved channels."""

import argparse
import csv
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e1-bnl"))
from compare import fits  # noqa: E402


SET_NAMES = {
    "b1": "FullSetB_1", "b2": "FullSetB_2", "c2": "FullSetC_2",
    "c3": "FullSetC_3", "d1": "FullSetD_1", "e1": "FullSetE_1",
    "e2": "FullSetE_2", "e3": "FullSetE_3", "f1": "FullSetF_1",
    "f2": "FullSetF_2", "g1": "FullSetG_1", "g2": "FullSetG_2",
}


def files(directory: Path, set_name: str) -> Path:
    stem = f"rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{set_name}"
    return directory / f"{stem}_Hists.root"


def quantile(values, q):
    vals = sorted(v for v in values if v is not None and math.isfinite(v))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = q * (len(vals) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return vals[lo]
    f = pos - lo
    return vals[lo] * (1.0 - f) + vals[hi] * f


def summary(values):
    vals = [v for v in values if v is not None and math.isfinite(v)]
    return {
        "count": len(vals),
        "median": quantile(vals, 0.50),
        "p90": quantile(vals, 0.90),
        "p95": quantile(vals, 0.95),
        "p99": quantile(vals, 0.99),
        "max": max(vals) if vals else None,
    }


def rel_diff(a, b):
    scale = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / scale


def log_ratio(a, b):
    if a <= 0 or b <= 0:
        return None
    return abs(math.log(a / b))


def shape(fit):
    w = fit["landau_width"]
    s = fit["gaussian_sigma"]
    m = fit["mpv"]
    return {
        "sigma_over_landau": s / w if w != 0 else None,
        "landau_over_mpv": w / m if m != 0 else None,
    }


def fmt(v):
    if v is None:
        return "-"
    return f"{v:.5g}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adaptive-root", required=True, type=Path)
    ap.add_argument("--candidate-root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    rows = []
    missing = []

    for code, set_name in SET_NAMES.items():
        a_path = files(args.adaptive_root / f"adaptive-fullset-{code}-repro" / "refine5", set_name)
        c_path = files(args.candidate_root / code / "refine5", set_name)
        for p in (a_path, c_path):
            if not p.is_file():
                missing.append(str(p))
        if not a_path.is_file() or not c_path.is_file():
            continue

        af = fits(a_path)
        cf = fits(c_path)
        for cell in sorted(af.keys() & cf.keys()):
            a = af[cell]
            c = cf[cell]
            sa = shape(a)
            sc = shape(c)
            row = {
                "set": code,
                "cell": cell,
                "adaptive_landau_width": a["landau_width"],
                "candidate_landau_width": c["landau_width"],
                "adaptive_mpv": a["mpv"],
                "candidate_mpv": c["mpv"],
                "adaptive_gaussian_sigma": a["gaussian_sigma"],
                "candidate_gaussian_sigma": c["gaussian_sigma"],
                "adaptive_chi2_ndf": a["chi2_ndf"],
                "candidate_chi2_ndf": c["chi2_ndf"],
                "adaptive_sigma_over_landau": sa["sigma_over_landau"],
                "candidate_sigma_over_landau": sc["sigma_over_landau"],
                "adaptive_landau_over_mpv": sa["landau_over_mpv"],
                "candidate_landau_over_mpv": sc["landau_over_mpv"],
                "rel_landau_width": rel_diff(a["landau_width"], c["landau_width"]),
                "rel_mpv": rel_diff(a["mpv"], c["mpv"]),
                "rel_gaussian_sigma": rel_diff(a["gaussian_sigma"], c["gaussian_sigma"]),
                "rel_chi2_ndf": (
                    rel_diff(a["chi2_ndf"], c["chi2_ndf"])
                    if a["chi2_ndf"] is not None and c["chi2_ndf"] is not None else None
                ),
                "log_sigma_over_landau_ratio": log_ratio(
                    sa["sigma_over_landau"], sc["sigma_over_landau"]
                ),
                "log_landau_over_mpv_ratio": log_ratio(
                    sa["landau_over_mpv"], sc["landau_over_mpv"]
                ),
            }
            row["max_shape_rel_diff"] = max(
                row["rel_landau_width"], row["rel_mpv"], row["rel_gaussian_sigma"]
            )
            rows.append(row)

    metrics = (
        "rel_landau_width", "rel_mpv", "rel_gaussian_sigma",
        "rel_chi2_ndf", "max_shape_rel_diff",
    )
    agreement = {m: summary([r[m] for r in rows]) for m in metrics}

    thresholds = [
        ("1pct_all", 0.01, 0.01, 0.01),
        ("1pct_mpv_5pct_widths", 0.01, 0.05, 0.05),
        ("5pct_all", 0.05, 0.05, 0.05),
        ("10pct_all", 0.10, 0.10, 0.10),
    ]
    cores = {}
    for name, mpv_lim, w_lim, s_lim in thresholds:
        core = [
            r for r in rows
            if r["rel_mpv"] <= mpv_lim
            and r["rel_landau_width"] <= w_lim
            and r["rel_gaussian_sigma"] <= s_lim
        ]
        cores[name] = {
            "count": len(core),
            "fraction": len(core) / len(rows) if rows else None,
            "candidate_sigma_over_landau": summary(
                [r["candidate_sigma_over_landau"] for r in core]
            ),
            "candidate_landau_over_mpv": summary(
                [r["candidate_landau_over_mpv"] for r in core]
            ),
            "candidate_chi2_ndf": summary(
                [r["candidate_chi2_ndf"] for r in core]
            ),
        }

    outliers = sorted(rows, key=lambda r: r["max_shape_rel_diff"], reverse=True)[:30]

    report = {
        "note": (
            "Method-agreement diagnostic only. Relative differences compare fits "
            "saved by both adaptive quadrature and the fixed-grid rescue replay."
        ),
        "common_fit_count": len(rows),
        "agreement": agreement,
        "provisional_agreement_cores": cores,
        "largest_shape_disagreements": outliers,
        "missing_files": sorted(set(missing)),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    csv_path = args.out.with_suffix(".csv")
    fields = list(rows[0].keys()) if rows else ["set", "cell"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Common saved fits: {len(rows)}")
    print()
    print("Adaptive vs fixed-grid relative differences:")
    print("metric                    median        p90        p95        p99        max")
    for m in metrics:
        s = agreement[m]
        print(
            f"{m:25s} {fmt(s['median']):>10s} {fmt(s['p90']):>10s} "
            f"{fmt(s['p95']):>10s} {fmt(s['p99']):>10s} {fmt(s['max']):>10s}"
        )

    print()
    print("Provisional agreement cores:")
    print("core                         count   fraction   sig/wL median [p05,p95]   wL/MPV median [p05,p95]")
    for name, info in cores.items():
        sr = info["candidate_sigma_over_landau"]
        wr = info["candidate_landau_over_mpv"]
        # summary() has p90/p95/p99 but not p05; calculate those here.
        core = [
            r for r in rows
            if (
                (name == "1pct_all" and r["rel_mpv"] <= .01 and r["rel_landau_width"] <= .01 and r["rel_gaussian_sigma"] <= .01)
                or (name == "1pct_mpv_5pct_widths" and r["rel_mpv"] <= .01 and r["rel_landau_width"] <= .05 and r["rel_gaussian_sigma"] <= .05)
                or (name == "5pct_all" and r["rel_mpv"] <= .05 and r["rel_landau_width"] <= .05 and r["rel_gaussian_sigma"] <= .05)
                or (name == "10pct_all" and r["rel_mpv"] <= .10 and r["rel_landau_width"] <= .10 and r["rel_gaussian_sigma"] <= .10)
            )
        ]
        sigs = [r["candidate_sigma_over_landau"] for r in core]
        widths = [r["candidate_landau_over_mpv"] for r in core]
        print(
            f"{name:28s} {info['count']:5d}   {info['fraction']:.3f}      "
            f"{fmt(quantile(sigs,.5)):>7s} [{fmt(quantile(sigs,.05))},{fmt(quantile(sigs,.95))}]   "
            f"{fmt(quantile(widths,.5)):>7s} [{fmt(quantile(widths,.05))},{fmt(quantile(widths,.95))}]"
        )

    print()
    print("Largest shape disagreements:")
    print("set cell   max-rel    dMPV       dLandau    dSigma     adaptive(sig/wL) candidate(sig/wL)")
    for r in outliers[:20]:
        print(
            f"{r['set']:3s} {r['cell']:4d}   {r['max_shape_rel_diff']:8.4g} "
            f"{r['rel_mpv']:8.4g} {r['rel_landau_width']:10.4g} "
            f"{r['rel_gaussian_sigma']:9.4g} "
            f"{r['adaptive_sigma_over_landau']:15.5g} {r['candidate_sigma_over_landau']:17.5g}"
        )

    print()
    print(f"Saved JSON: {args.out}")
    print(f"Saved CSV:  {csv_path}")

    if missing:
        for p in sorted(set(missing)):
            print(f"MISSING {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
