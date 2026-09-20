#!/usr/bin/env python3
"""Run the two existing HV44 seeds with fixed/adaptive integration, without changing bounds."""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def number(text: str, precision: int = 7) -> str:
    """Preserve NaNs and errors rather than formatting them as zero."""
    try:
        x = float(text)
    except (ValueError, TypeError):
        return str(text)
    return format(x, f".{precision}g") if math.isfinite(x) else str(text)


def show(paths):
    print("case seed status fit_valid cov calls min_FCN EDM gate numerics peak FWHM")
    for path in paths:
        with Path(path).open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            needed = {"integrator", "result_valid", "cov_status", "n_calls", "min_fcn", "edm",
                      "fit_status", "legacy_fit_gate_pass", "numerics_pass", "numerics_complete",
                      "adaptive_peak", "adaptive_fwhm", "peak", "fwhm", "width", "gsigma"}
            if not needed.issubset(reader.fieldnames or []):
                raise ValueError(f"{path}: not an adaptive-refit CSV")
            rows = list(reader)
        if not rows:
            raise ValueError(f"{path}: empty result table")
        for i, r in enumerate(rows, 1):
            adaptive = r["integrator"] == "adaptive"
            flag = ("PASS" if r["numerics_pass"] == "1" else "CHECK") if adaptive else "legacy"
            if adaptive and r["numerics_complete"] != "1":
                flag = "ERROR"
            peak = r["adaptive_peak"] if adaptive else r["peak"]
            width = r["adaptive_fwhm"] if adaptive else r["fwhm"]
            print(Path(path).stem, i, r["fit_status"], r["result_valid"], r["cov_status"],
                  r["n_calls"], number(r["min_fcn"]), number(r["edm"]),
                  r["legacy_fit_gate_pass"], flag, number(peak, 10), number(width, 10))
            print("  LandauWidth=" + number(r["width"], 10), "GSigma=" + number(r["gsigma"], 10),
                  "bounds=" + (r.get("boundary_parameters") or "none"))
            if r.get("numerics_error"):
                print("  numerical check:", r["numerics_error"])
    print("PASS concerns fixed-parameter curve checks only; gate/fit validity remain separate.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, help="existing hv44-delete-test output directory")
    p.add_argument("--fitter", type=Path, default=Path(__file__).resolve().parent / "build/fit_cell903")
    p.add_argument("--out", type=Path, help="new result directory; must not exist")
    p.add_argument("--show", nargs="+", type=Path, help="only summarize existing refit CSVs")
    a = p.parse_args()
    if a.show:
        show(a.show)
        return 0
    if a.work is None:
        p.error("--work is required unless --show is used")
    work = a.work.expanduser().resolve()
    fitter = a.fitter.expanduser().resolve()
    hist = work / "refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_Hists.root"
    c1 = work / "refine1/rawHGCROC_wPedwMuon_wBC_ImpR_194_calib.txt"
    c2 = work / "refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_calib.txt"
    for path in (fitter, hist, c1, c2):
        if not path.is_file():
            raise ValueError(f"missing input: {path}")
    if not os.access(str(fitter), os.X_OK):
        raise ValueError(f"not executable: {fitter}")
    if a.out is not None:
        out = a.out.expanduser().resolve()
        out.mkdir(parents=True, exist_ok=False)
    else:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
        out = Path(tempfile.mkdtemp(prefix="adaptive-refit-" + stamp, dir=str(work)))
    print("Results:", out, flush=True)
    checked_paths = (fitter, c1, c2)
    hashes = {str(x): digest(x) for x in checked_paths}
    metadata = {"schema": 1, "hostname": platform.node(), "platform": platform.platform(),
                "file_sha256": hashes,
                "histogram": {"path": str(hist), "size": hist.stat().st_size,
                              "mtime_ns": hist.stat().st_mtime_ns, "sha256": None},
                "note": "Histogram is not hashed; its actual TH1 is saved in each result ROOT file.",
                "environment": {k: os.environ[k] for k in ("ROOT_MAX_THREADS", "OMP_NUM_THREADS") if k in os.environ},
                "cases": []}
    def save():
        (out / "run.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    cases = [("fixed100", ["--integrator", "fixed", "--steps", "100"]),
             ("adaptive_1e-8", ["--integrator", "adaptive", "--quad-rtol", "1e-8"]),
             ("adaptive_1e-10", ["--integrator", "adaptive", "--quad-rtol", "1e-10"])]
    outputs = []
    for label, options in cases:
        output = out / (label + ".csv")
        command = [str(fitter), str(hist), "--calib", str(c1), "--calib", str(c2)]
        command += options + ["--csv", str(output), "--results-root", str(out / (label + ".root"))]
        log = out / (label + ".log")
        entry = {"case": label, "argv": command, "log": str(log), "returncode": None}
        metadata["cases"].append(entry)
        save()
        print("Running", label, "(two seeds; log:", str(log) + ")", flush=True)
        with log.open("w", encoding="utf-8") as f:
            completed = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, check=False)
        entry["returncode"] = completed.returncode
        save()
        if completed.returncode:
            print(log.read_text(encoding="utf-8", errors="replace")[-5000:], file=sys.stderr)
            raise RuntimeError(f"{label} failed with exit {completed.returncode}; outputs preserved in {out}")
        with output.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if len(rows) != 2:
            raise RuntimeError(f"{label}: expected two seed rows, found {len(rows)}")
        outputs.append(output)
    if hashes != {str(x): digest(x) for x in checked_paths}:
        raise RuntimeError("executable or calibration input changed during the experiment")
    show(outputs)
    print("Results:", out)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as e:
        print("run_adaptive_refits:", e, file=sys.stderr)
        raise SystemExit(1)
