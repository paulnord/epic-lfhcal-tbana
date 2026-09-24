#!/usr/bin/env python3
"""Paired fixed/adaptive fits with starts varied and setup held constant.

The cases JSON is a list of records with case_id, input, hist_key, calib,
cell_id, layers and vov. Output must be a new directory. Each fit runs in a
fresh process and preserves its CSV, ROOT result, log and exact command.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import time

from run_adaptive_refits import code_provenance, utc_now


STARTS = {
    "base": None,
    "width_lo": ("width", 0.8), "width_hi": ("width", 1.2),
    "mp_lo": ("mp", 0.98), "mp_hi": ("mp", 1.02),
    "sigma_lo": ("gsigma", 0.8), "sigma_hi": ("gsigma", 1.2),
}
PARAMETERS = ("width", "mp", "area", "gsigma")
FROZEN = ("avmip", "ped_sigma", "active_channels", "min_x", "fit_low", "fit_high", "int_area") + tuple(
    f"{p}_{side}" for p in PARAMETERS for side in ("low", "high"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_row(path):
    with Path(path).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1 or None in rows[0] or any(v is None for v in rows[0].values()):
        raise ValueError(f"expected exactly one intact fit row: {path}")
    needed = set(FROZEN) | {f"start_{p}" for p in PARAMETERS} | {"fit_status", "integrator", "fit_option"}
    if not needed.issubset(rows[0]):
        raise ValueError(f"missing setup fields: {path}")
    return rows[0]


def start_values(base, start_name):
    values = {p: float(base[f"start_{p}"]) for p in PARAMETERS}
    change = STARTS[start_name]
    if change:
        parameter, factor = change
        values[parameter] *= factor
    for parameter, value in values.items():
        if not (math.isfinite(value) and float(base[f"{parameter}_low"]) < value < float(base[f"{parameter}_high"])):
            raise ValueError(f"{start_name}: {parameter} start not strictly interior")
    return values


def verify_setup(row, base, integrator, start_name, fit_option):
    for key in FROZEN:
        if float(row[key]) != float(base[key]):
            raise ValueError(f"frozen setup changed: {key}: {base[key]} -> {row[key]}")
    for parameter, value in start_values(base, start_name).items():
        if not math.isclose(float(row[f"start_{parameter}"]), value, rel_tol=2e-15, abs_tol=0):
            raise ValueError(f"wrong start for {parameter}")
    if row["integrator"] != integrator or row["fit_option"] != fit_option:
        raise ValueError("wrong integration method or fit option")


def load_cases(path):
    cases = json.loads(Path(path).read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty JSON list")
    seen = set()
    for case in cases:
        for key in ("case_id", "input", "hist_key", "calib", "cell_id", "layers", "vov"):
            if key not in case:
                raise ValueError(f"missing case field {key}")
        identifier = case["case_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier) or identifier in seen:
            raise ValueError("unsafe or duplicate case_id")
        seen.add(identifier)
        for field in ("input", "calib"):
            case[field] = str(Path(case[field]).expanduser().resolve(strict=True))
        if not math.isfinite(float(case["vov"])) or int(case["layers"]) < 1:
            raise ValueError("invalid voltage or segment geometry")
    return cases


def command(fitter, case, integrator, start_name, base, out, fit_option):
    stem = out / "fits" / case["case_id"] / f"{integrator}__{start_name}"
    paths = {suffix: str(stem.with_suffix("." + suffix)) for suffix in ("csv", "root", "log")}
    argv = [str(fitter), case["input"], "--hist", case["hist_key"],
            "--calib", case["calib"], "--cell", str(case["cell_id"]),
            "--layers", str(case["layers"]), "--vov", str(case["vov"]),
            "--fit-option", fit_option, "--integrator", integrator,
            "--steps", "100", "--quad-rtol", "1e-10", "--repeat", "1",
            "--csv", paths["csv"], "--results-root", paths["root"]]
    if STARTS[start_name]:
        values = start_values(base, start_name)
        parameter = STARTS[start_name][0]
        argv += ["--start-" + parameter, repr(values[parameter])]
    return argv, paths


def run_one(fitter, case, integrator, start_name, base, out, fit_option):
    argv, paths = command(fitter, case, integrator, start_name, base, out, fit_option)
    result = dict(case_id=case["case_id"], fit_id=f"{integrator}__{start_name}",
                  integrator=integrator, start_name=start_name, argv=argv, paths=paths,
                  started_utc=utc_now(), returncode=None, setup_verified=False)
    started = time.monotonic()
    env = dict(os.environ, ROOT_MAX_THREADS="1", OMP_NUM_THREADS="1")
    try:
        with Path(paths["log"]).open("x") as log:
            process = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, env=env, check=False)
        result["returncode"] = process.returncode
        if process.returncode != 0:
            raise ValueError(f"fitter process failed: {process.returncode}")
        row = read_row(paths["csv"])
        if not Path(paths["root"]).is_file():
            raise ValueError("missing ROOT result")
        verify_setup(row, base or row, integrator, start_name, fit_option)
        result.update(setup_verified=True, fit_status=row["fit_status"])
    except (OSError, ValueError) as error:
        result["automation_error"] = str(error)
    result.update(elapsed_seconds=time.monotonic()-started, finished_utc=utc_now())
    result["output_sha256"] = {key: digest(value) for key, value in paths.items() if Path(value).is_file()}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--fitter", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fit-option", choices=("QRLMN0", "QRLN0"), default="QRLMN0")
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    cases = load_cases(args.cases)
    fitter = args.fitter.resolve(strict=True)
    if not os.access(fitter, os.X_OK):
        raise ValueError("fitter is not executable")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for case in cases:
        (out / "fits" / case["case_id"]).mkdir(parents=True)
    files = {str(fitter), str(args.cases.resolve())} | {c[k] for c in cases for k in ("input", "calib")}
    study = Path(__file__).resolve().parent
    files |= {str(p) for p in study.iterdir() if p.suffix in (".cc", ".h", ".py") or p.name == "CMakeLists.txt"}
    before = {p: digest(p) for p in sorted(files)}
    manifest = dict(schema=1, created_utc=utc_now(), hostname=platform.node(), platform=platform.platform(),
                    cases=cases, fits=[], fit_option=args.fit_option,
                    protocol="fixed100 vs adaptive1e-10, same +/-5sigma, original bounds/range/budgets, seven starts",
                    starts=STARTS, environment={"ROOT_MAX_THREADS": "1", "OMP_NUM_THREADS": "1"},
                    workers=args.jobs, input_and_code_sha256=before, code=code_provenance(out))

    def save():
        temp = out / "manifest.json.tmp"
        temp.write_text(json.dumps(manifest, indent=2) + "\n")
        temp.replace(out / "manifest.json")

    def collect(futures):
        for future in as_completed(futures):
            result = future.result()
            manifest["fits"].append(result)
            save()
            print(f"{len(manifest['fits'])}/{len(cases)*14} {result['case_id']} {result['fit_id']} "
                  f"status={result.get('fit_status', 'missing')} {result['elapsed_seconds']:.1f}s "
                  f"{result.get('automation_error', '')}", flush=True)

    save()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        collect([pool.submit(run_one, fitter, c, "fixed", "base", None, out, args.fit_option) for c in cases])
        good = {r["case_id"]: r for r in manifest["fits"] if r["setup_verified"]}
        futures = []
        for case in cases:
            if case["case_id"] not in good:
                continue
            base = read_row(good[case["case_id"]]["paths"]["csv"])
            # Validate every perturbation before launching any dependent fit.
            for start in STARTS:
                start_values(base, start)
            for integrator in ("fixed", "adaptive"):
                for start in STARTS:
                    if (integrator, start) != ("fixed", "base"):
                        futures.append(pool.submit(run_one, fitter, case, integrator, start, base, out, args.fit_option))
        collect(futures)
    manifest["finished_utc"] = utc_now()
    manifest["inputs_and_code_unchanged"] = all(digest(p) == value for p, value in before.items())
    manifest["automation_pass"] = (len(manifest["fits"]) == len(cases)*14 and
                                     all(r["setup_verified"] for r in manifest["fits"]) and
                                     manifest["inputs_and_code_unchanged"])
    save()
    return 0 if manifest["automation_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
