#!/usr/bin/env python3
"""Run controlled isolated HV44 refits using the two existing calibration seeds."""
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
import time


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def code_provenance(out: Path):
    """Save tracked changes in this isolated study; report unavailable Git honestly."""
    study = Path(__file__).resolve().parent
    code = {"study_path": str(study), "git_commit": None,
            "diff_path": None, "diff_sha256": None,
            "diff_scope": "git diff --binary HEAD -- . in study directory; tracked files only"}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=study,
                                capture_output=True, text=True, check=True)
        changes = subprocess.run(["git", "diff", "--binary", "HEAD", "--", "."],
                                 cwd=study, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        code["error"] = str(error)
        return code
    patch = out / "isolated-study.patch"
    patch.write_bytes(changes.stdout)
    code.update(git_commit=commit.stdout.strip(), diff_path=str(patch), diff_sha256=digest(patch))
    return code


def number(text: str, precision: int = 7) -> str:
    """Preserve NaNs and errors rather than formatting them as zero."""
    try:
        x = float(text)
    except (ValueError, TypeError):
        return str(text)
    return format(x, f".{precision}g") if math.isfinite(x) else str(text)


def read_rows(path):
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
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{path}: malformed CSV row")
        if row["integrator"] not in ("fixed", "adaptive"):
            raise ValueError(f"{path}: unknown integrator in CSV")
    return rows


def show(paths):
    print("case seed status fit_valid cov calls min_FCN EDM gate numerics peak FWHM")
    for path in paths:
        rows = read_rows(path)
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
    p.add_argument("--experiment", choices=("adaptive", "gsigma-bound"), default="adaptive",
                   help="adaptive: original three cases; gsigma-bound: no-M baseline and cap 58.129")
    p.add_argument("--histogram", type=Path, help="explicit input ROOT file instead of the refine2 file")
    p.add_argument("--histogram-key", help="explicit TH1 key, e.g. source_histogram in a saved result")
    p.add_argument("--calib", type=Path, action="append",
                   help="explicit calibration seed; supply exactly twice in seed order")
    p.add_argument("--show", nargs="+", type=Path, help="only summarize existing refit CSVs")
    a = p.parse_args()
    if a.show:
        show(a.show)
        return 0
    if a.calib is not None and len(a.calib) != 2:
        p.error("--calib must be supplied exactly twice")
    if a.work is None and (a.histogram is None or a.calib is None):
        p.error("provide --work or an explicit --histogram and two --calib inputs")
    if a.work is None and a.out is None:
        p.error("--out is required when --work is omitted")
    if a.experiment == "gsigma-bound" and a.out is None:
        p.error("--out is required for --experiment gsigma-bound")
    work = a.work.expanduser().resolve() if a.work is not None else None
    fitter = a.fitter.expanduser().resolve()
    hist = (a.histogram.expanduser().resolve() if a.histogram is not None else
            work / "refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_Hists.root")
    if a.calib is not None:
        c1, c2 = (path.expanduser().resolve() for path in a.calib)
    else:
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
    checked_paths = (fitter, c1, c2, hist)
    hashes = {str(x): digest(x) for x in checked_paths}
    metadata = {"schema": 2, "hostname": platform.node(), "platform": platform.platform(),
                "created_utc": utc_now(), "code": code_provenance(out),
                "experiment": a.experiment,
                "file_sha256": hashes,
                "histogram": {"path": str(hist), "key": a.histogram_key, "size": hist.stat().st_size,
                              "mtime_ns": hist.stat().st_mtime_ns, "sha256": hashes[str(hist)]},
                "note": "All input files are hashed; the actual TH1 is saved in each result ROOT file.",
                "environment": {k: os.environ[k] for k in ("ROOT_MAX_THREADS", "OMP_NUM_THREADS") if k in os.environ},
                "cases": []}
    def save():
        (out / "run.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    cases = [("fixed100", ["--integrator", "fixed", "--steps", "100"]),
             ("adaptive_1e-8", ["--integrator", "adaptive", "--quad-rtol", "1e-8"]),
             ("adaptive_1e-10", ["--integrator", "adaptive", "--quad-rtol", "1e-10"])]
    if a.experiment == "gsigma-bound":
        controls = ["--integrator", "adaptive", "--quad-rtol", "1e-10", "--fit-option", "QRLN0"]
        cases = [("adaptive_noM_1e-10", controls),
                 ("adaptive_sigma58", controls + ["--gsigma-high", "58.129"])]
    outputs = []
    for label, options in cases:
        output = out / (label + ".csv")
        command = [str(fitter), str(hist), "--calib", str(c1), "--calib", str(c2)]
        if a.histogram_key is not None:
            command += ["--hist", a.histogram_key]
        command += options + ["--csv", str(output), "--results-root", str(out / (label + ".root"))]
        log = out / (label + ".log")
        entry = {"case": label, "argv": command, "log": str(log), "returncode": None,
                 "started_utc": None, "finished_utc": None, "elapsed_seconds": None}
        metadata["cases"].append(entry)
        save()
        print("Running", label, "(two seeds; log:", str(log) + ")", flush=True)
        with log.open("w", encoding="utf-8") as f:
            entry["started_utc"] = utc_now()
            save()
            started = time.monotonic()
            try:
                completed = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, check=False)
                entry["returncode"] = completed.returncode
            except OSError as error:
                entry["error"] = str(error)
                raise
            finally:
                entry["elapsed_seconds"] = time.monotonic() - started
                entry["finished_utc"] = utc_now()
                save()
        if completed.returncode:
            print(log.read_text(encoding="utf-8", errors="replace")[-5000:], file=sys.stderr)
            raise RuntimeError(f"{label} failed with exit {completed.returncode}; outputs preserved in {out}")
        rows = read_rows(output)
        if len(rows) != 2:
            raise RuntimeError(f"{label}: expected two seed rows, found {len(rows)}")
        outputs.append(output)
        if hashes != {str(x): digest(x) for x in checked_paths}:
            raise RuntimeError("executable, calibration, or histogram input changed during the experiment")
    show(outputs)
    print("Results:", out)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as e:
        print("run_adaptive_refits:", e, file=sys.stderr)
        raise SystemExit(1)
