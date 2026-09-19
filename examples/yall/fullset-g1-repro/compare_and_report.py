#!/usr/bin/env python3
"""Compare the FullSet G1 reproduction and assemble calibration PDF plot books.

Run from examples/yall/fullset-g1-repro after:
    source env.tcsh
    python3 compare_and_report.py

Uses only Python's standard library plus pdfunite.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

COLUMNS = (
    "cell_id", "layer", "row", "column", "module",
    "ped_mean_h", "ped_sigma_h", "ped_mean_l", "ped_sigma_l",
    "mip_scale_h", "mip_width_h", "mip_scale_l", "mip_width_l",
    "lghg_corr", "lghg_corr_offset", "hglg_corr",
    "hglg_corr_offset_toa", "bc",
)
INT_FIELDS = {"cell_id", "layer", "row", "column", "module", "bc"}
STAGES = ("pedestal", "mip", "refine1", "refine2", "refine3", "refine4", "refine5", "final")


def args():
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    work = Path(os.environ.get("LFHCAL_WORK", ".")) / "fullset-g1-repro"
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=work)
    p.add_argument("--reference", type=Path,
                   default=repo / "calibrations/TB2026/calib_SPS-H2_FullSetG_1.txt")
    p.add_argument("--set-name", default="FullSetG_1")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--no-pdf", action="store_true")
    return p.parse_args()


def parse_calib(path):
    rows = {}
    payload = path.read_bytes()
    for line_no, line in enumerate(payload.decode("utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith(("#", "%")) or s.startswith("RunNr:"):
            continue
        fields = s.split()
        if not fields or not fields[0].isdigit():
            continue
        if len(fields) != len(COLUMNS):
            raise ValueError(f"{path}:{line_no}: expected 18 columns, got {len(fields)}")
        row = {}
        for name, token in zip(COLUMNS, fields):
            value = Decimal(token)
            if name in INT_FIELDS:
                if value != int(value):
                    raise ValueError(f"{path}:{line_no}: non-integer {name}")
                value = int(value)
            row[name] = value
        cell = row["cell_id"]
        if cell in rows:
            raise ValueError(f"{path}: duplicate cell {cell}")
        rows[cell] = row
    if not rows:
        raise ValueError(f"{path}: no calibration records")
    return rows, payload


def one_calib(directory):
    files = sorted(directory.glob("*_calib.txt"))
    if len(files) != 1:
        raise ValueError(f"expected one *_calib.txt in {directory}, found {len(files)}")
    return files[0]


def pct(ref, got):
    return float(100 * (got - ref) / ref) if ref > 0 and got > 0 else None


def percentile(values, q):
    if not values:
        return None
    x = sorted(values)
    pos = (len(x) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return x[lo] + (x[hi] - x[lo]) * (pos - lo)


def stats(values):
    if not values:
        return {"n": 0}
    a = [abs(x) for x in values]
    return {
        "n": len(values),
        "median_abs_pct": statistics.median(a),
        "p95_abs_pct": percentile(a, .95),
        "rms_pct": math.sqrt(statistics.mean(x*x for x in values)),
        "max_abs_pct": max(a),
    }


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def compare(work, reference_path, out, set_name):
    ref, ref_bytes = parse_calib(reference_path)
    tables = {"reference": ref}
    payloads = {"reference": ref_bytes}
    paths = {"reference": reference_path}

    for stage in STAGES:
        path = one_calib(work / stage)
        tables[stage], payloads[stage] = parse_calib(path)
        paths[stage] = path

    ids = sorted(ref)
    for stage, table in tables.items():
        if set(table) != set(ref):
            raise ValueError(f"{stage}: cell-ID set differs from reference")
        bad = [i for i in ids if any(
            table[i][x] != ref[i][x] for x in ("layer", "row", "column", "module")
        )]
        if bad:
            raise ValueError(f"{stage}: geometry mismatch, first cells {bad[:10]}")

    final = tables["final"]
    final_rows = []
    for i in ids:
        a, b = ref[i], final[i]
        row = {k: a[k] for k in ("cell_id", "module", "layer", "row", "column")}
        for field in ("mip_scale_h", "mip_width_h",
                      "ped_mean_h", "ped_sigma_h", "ped_mean_l", "ped_sigma_l"):
            row[f"{field}_reference"] = a[field]
            row[f"{field}_reproduced"] = b[field]
            row[f"{field}_delta"] = b[field] - a[field]
            if field.startswith("mip_"):
                row[f"{field}_pct_delta"] = pct(a[field], b[field])
        final_rows.append(row)

    def metric(table, field):
        d = {i: pct(ref[i][field], table[i][field]) for i in ids}
        d = {i: v for i, v in d.items() if v is not None}
        s = stats(list(d.values()))
        if d:
            s["max_pct_cell"] = max(d, key=lambda i: abs(d[i]))
            s["exact_equal"] = sum(ref[i][field] == table[i][field] for i in d)
            s["within_0.001_pct"] = sum(abs(v) <= .001 for v in d.values())
            s["within_0.01_pct"] = sum(abs(v) <= .01 for v in d.values())
        return s

    scale = metric(final, "mip_scale_h")
    width = metric(final, "mip_width_h")

    stage_rows = []
    for stage in ("mip", "refine1", "refine2", "refine3", "refine4", "refine5", "final"):
        s = metric(tables[stage], "mip_scale_h")
        stage_rows.append({"stage": stage, **s})

    unavailable = [i for i in ids if ref[i]["mip_scale_h"] <= 0 or final[i]["mip_scale_h"] <= 0]
    restored = [i for i in ids
                if tables["mip"][i]["mip_scale_h"] <= 0
                and tables["refine1"][i]["mip_scale_h"] > 0]
    bc_mismatch = [i for i in ids if ref[i]["bc"] != final[i]["bc"]]

    comparison = out / "comparison"
    comparison.mkdir(parents=True, exist_ok=True)
    write_csv(comparison / "final_comparison.csv", final_rows)
    write_csv(comparison / "stage_summary.csv", stage_rows)

    summary = {
        "set": set_name,
        "reference": str(reference_path),
        "reproduced": str(paths["final"]),
        "cells": len(ids),
        "mip_scale_h": scale,
        "mip_width_h": width,
        "bc_mismatch_ids": bc_mismatch,
        "unavailable_mip_ids": unavailable,
        "restored_at_refine1_ids": restored,
        "final_identical_to_refine5_bytes": payloads["final"] == payloads["refine5"],
    }
    (comparison / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    lines = [
        f"{set_name} calibration comparison",
        f"Reference:  {reference_path}",
        f"Reproduced: {paths['final']}",
        f"Cells: {len(ids)}",
        "",
        "HG MIP scale",
        f"  positive pairs: {scale['n']}",
        f"  exact at exported precision: {scale.get('exact_equal', 0)}",
        f"  median |relative difference|: {scale['median_abs_pct']:.9f}%",
        f"  95th percentile: {scale['p95_abs_pct']:.9f}%",
        f"  RMS: {scale['rms_pct']:.9f}%",
        f"  maximum: {scale['max_abs_pct']:.9f}% at cell {scale.get('max_pct_cell')}",
        f"  within 0.001%: {scale.get('within_0.001_pct', 0)}/{scale['n']}",
        f"  within 0.01%: {scale.get('within_0.01_pct', 0)}/{scale['n']}",
        "",
        "Stored HG MIP width",
        f"  median |relative difference|: {width['median_abs_pct']:.9f}%",
        f"  maximum: {width['max_abs_pct']:.9f}% at cell {width.get('max_pct_cell')}",
        "",
        f"BC mismatches: {bc_mismatch}",
        f"Unavailable/nonpositive HG MIP cells: {unavailable}",
        f"Recovered at refine1: {restored}",
        f"Final byte-identical to refine5: {summary['final_identical_to_refine5_bytes']}",
        "",
        "Convergence vs reference (HG MIP scale)",
    ]
    for row in stage_rows:
        lines.append(
            f"  {row['stage']:7s} n={row['n']:3d} "
            f"median |d|={row['median_abs_pct']:.9f}% "
            f"max |d|={row['max_abs_pct']:.9f}%"
        )
    text = "\n".join(lines) + "\n"
    (comparison / "comparison.txt").write_text(text)
    print(text, end="")


def natural(paths):
    def key(path):
        return [int(x) if x.isdigit() else x.lower()
                for x in re.split(r"(\d+)", path.name)]
    return sorted(paths, key=key)


def exact(directory, names):
    files, missing = [], []
    for name in names:
        path = directory / name
        (files if path.is_file() else missing).append(path if path.is_file() else name)
    return files, missing


def mip_inputs(directory, initial):
    suffix = "_2nd" if initial else ""
    head = [
        f"HG_FWHMMip{suffix}.pdf",
        f"HG_GaussSigMip{suffix}.pdf",
        f"HG_LandMPVMip{suffix}.pdf",
        f"HG_LandSigMip{suffix}.pdf",
        f"HG_MaxMip{suffix}.pdf",
        "HGscaleChi2VsLayer.pdf",
    ]
    tail = [
        "MipTriggXY.pdf",
        "MuonTriggers.pdf",
        "SNRTriggVsLayer.pdf",
        "SuppressionNoise.pdf",
        "SuppressionSignal.pdf",
    ]
    files, missing = exact(directory, head)
    mip_layers = natural(directory.glob("MIP_HG_Layer*.pdf"))
    if mip_layers:
        files += mip_layers
    else:
        missing.append("MIP_HG_Layer*.pdf")
    got, miss = exact(directory, tail)
    files += got
    missing += miss
    trig_layers = natural(directory.glob("TriggPrimitive_Layer*.pdf"))
    if trig_layers:
        files += trig_layers
    else:
        missing.append("TriggPrimitive_Layer*.pdf")
    return files, missing


def unite(output, inputs):
    if not inputs:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    if len(inputs) == 1:
        shutil.copyfile(inputs[0], output)
        return
    exe = shutil.which("pdfunite")
    if not exe:
        raise RuntimeError("pdfunite not found in PATH")
    subprocess.run([exe, *map(str, inputs), str(output)], check=True)


def make_pdfs(work, out, set_name):
    report_dir = out / "pdf"
    report_dir.mkdir(parents=True, exist_ok=True)
    plots = work / "plots"
    muon = f"Muon_{set_name}"

    stages = [
        ("mip", "Initial", True),
        ("refine1", "ImpR", False),
        ("refine2", "Imp2R", False),
        ("refine3", "Imp3R", False),
        ("refine4", "Imp4R", False),
        ("refine5", "Imp5R", False),
    ]
    made = {}
    for stage, label, initial in stages:
        directory = plots / stage / muon
        if not directory.is_dir():
            print(f"PDF: skip {stage}; no {directory}", file=sys.stderr)
            continue
        files, missing = mip_inputs(directory, initial)
        if missing:
            print(f"PDF: {stage} missing: {', '.join(map(str, missing))}", file=sys.stderr)
        if files:
            output = report_dir / f"SummaryMipCalibration_{label}_{set_name}.pdf"
            unite(output, files)
            made[stage] = output
            print(f"PDF: wrote {output} from {len(files)} plots")

    if "refine5" in made:
        final = report_dir / f"SummaryMipCalibration_Final_{set_name}.pdf"
        shutil.copyfile(made["refine5"], final)
        made["final"] = final
        print(f"PDF: wrote {final}")

    for stage, label in (("pedestal", "Pedestal"), ("transfer", "Transfer")):
        root = plots / stage
        files = natural(root.rglob("*.pdf")) if root.is_dir() else []
        if files:
            output = report_dir / f"Summary{label}_{set_name}.pdf"
            unite(output, files)
            made[stage] = output
            print(f"PDF: wrote {output} from {len(files)} plots")

    parts = [made[x] for x in ("pedestal", "transfer", "final") if x in made]
    if parts:
        output = report_dir / f"CalibrationPlotBook_{set_name}.pdf"
        unite(output, parts)
        print(f"PDF: wrote {output}")


def main():
    a = args()
    work = a.work.resolve()
    out = (a.out or work / "report").resolve()
    reference = a.reference.resolve()
    try:
        out.mkdir(parents=True, exist_ok=True)
        compare(work, reference, out, a.set_name)
        if not a.no_pdf:
            make_pdfs(work, out, a.set_name)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"Report directory: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
