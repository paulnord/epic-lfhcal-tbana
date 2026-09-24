#!/usr/bin/env python3
"""Run the complete adaptive-fit validation protocol and write an audit bundle.

The protocol is deliberately layered.  Fast source/unit checks run first; ROOT
fit comparisons, start-value stability, and production-campaign audits are
optional phases because they may take hours on BNL.  Every phase records its
exact command, environment, elapsed time, return code, and log path in
``manifest.json``.  A nonzero phase is a failure; an unavailable optional
input is a warning, never an implicit pass.

This script does not modify calibration outputs.  Its output directory must be
new, which makes reruns and comparisons unambiguous.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time


STUDY = Path(__file__).resolve().parent
REPO = STUDY.parents[3]
DEFAULT_E1 = REPO / "local-results/fullset-e1-adaptive-review-20260921/imported/fullset-e1-repro/refine5"
DEFAULT_CASES = REPO / "local-results/hv-stability-20260920/cases.json"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_phase(manifest: dict, name: str, argv: list[str], out: Path, *, optional=False,
              cwd: Path | None = None, env_extra: dict[str, str] | None = None) -> bool:
    log = out / "logs" / f"{name}.log"
    entry = {"name": name, "argv": argv, "cwd": str(cwd or Path.cwd()),
             "optional": optional, "log": str(log), "started_utc": utc_now(),
             "returncode": None, "status": "running"}
    manifest["phases"].append(entry)
    write_json(out / "manifest.json", manifest)
    env = os.environ.copy()
    env.update({"ROOT_MAX_THREADS": "1", "OMP_NUM_THREADS": "1"})
    if env_extra:
        env.update(env_extra)
    started = time.monotonic()
    try:
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, check=False)
        entry["returncode"] = result.returncode
        entry["status"] = "pass" if result.returncode == 0 else "fail"
    except OSError as error:
        entry["status"] = "fail"
        entry["error"] = str(error)
    entry["elapsed_seconds"] = time.monotonic() - started
    entry["finished_utc"] = utc_now()
    write_json(out / "manifest.json", manifest)
    print(f"[{entry['status']}] {name} ({entry['elapsed_seconds']:.1f}s)", flush=True)
    return entry["status"] == "pass"


def skip_phase(manifest: dict, name: str, reason: str, out: Path) -> None:
    manifest["phases"].append({"name": name, "status": "warn", "reason": reason,
                                "started_utc": utc_now(), "finished_utc": utc_now()})
    write_json(out / "manifest.json", manifest)
    print(f"[warn] {name}: {reason}", flush=True)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def configure_and_test(manifest: dict, out: Path, build: Path, jobs: int) -> None:
    run_phase(manifest, "configure", ["cmake", "-S", str(STUDY), "-B", str(build)], out)
    run_phase(manifest, "build", ["cmake", "--build", str(build), "-j", str(jobs)], out)
    run_phase(manifest, "ctest", ["ctest", "--test-dir", str(build), "--output-on-failure"], out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new audit directory")
    parser.add_argument("--build", type=Path, default=STUDY / "build-monster")
    parser.add_argument("--e1-dir", type=Path, default=DEFAULT_E1)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--fitter", type=Path, help="fit_cell903 executable")
    parser.add_argument("--campaign", type=Path, action="append", default=[],
                        help="completed BNL campaign directory to audit")
    parser.add_argument("--calibration-work", type=Path, action="append", default=[],
                        help="completed fullset output tree to compare with its published calibration")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-tool-comparison", action="store_true")
    parser.add_argument("--skip-stability", action="store_true")
    parser.add_argument("--skip-campaign-audit", action="store_true")
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    if out.exists():
        parser.error(f"output already exists: {out}")
    out.mkdir(parents=True)
    (out / "logs").mkdir()
    (out / "results").mkdir()
    manifest = {
        "schema": 1, "protocol": "monster-adaptive-fit-validation", "created_utc": utc_now(),
        "host": platform.node(), "platform": platform.platform(), "python": sys.version,
        "study": str(STUDY), "repo": str(REPO), "phases": [], "warnings": [],
        "inputs": {}, "environment": {k: os.environ.get(k) for k in
                                         ("ROOT_MAX_THREADS", "OMP_NUM_THREADS", "PYTHONPATH")},
    }
    tracked = [p for p in STUDY.iterdir() if p.is_file() and p.suffix in {".cc", ".h", ".py"}]
    manifest["study_sha256"] = {str(p): sha256(p) for p in sorted(tracked)}
    for label, path in (("e1_dir", args.e1_dir), ("cases", args.cases)):
        manifest["inputs"][label] = {"path": str(path), "exists": path.exists()}
        if path.is_file():
            manifest["inputs"][label]["sha256"] = sha256(path)
    write_json(out / "manifest.json", manifest)

    if not args.skip_build:
        configure_and_test(manifest, out, args.build.expanduser().resolve(), args.jobs)
    else:
        skip_phase(manifest, "build-and-ctest", "requested with --skip-build", out)

    for test_name in ("test_adaptive_runner.py", "test_fit_stability_runner.py",
                      "test_collect_hv_histograms.py", "test_analyze_hv_histograms.py"):
        test = STUDY / test_name
        if not test.exists():
            skip_phase(manifest, test_name, "test file is absent", out)
        elif not command_exists("python3"):
            skip_phase(manifest, test_name, "python3 is unavailable", out)
        else:
            run_phase(manifest, test_name.removesuffix(".py"), ["python3", str(test)], out,
                      env_extra={"PYTHONDONTWRITEBYTECODE": "1"})

    fitter = (args.fitter or (args.build / "fit_cell903")).expanduser().resolve()
    if not args.skip_tool_comparison:
        comparison = STUDY / "compare_langau_tools.py"
        if not comparison.exists() or not args.e1_dir.is_dir():
            skip_phase(manifest, "langau-tool-comparison", "E1 histogram directory unavailable", out)
        elif not command_exists("python3"):
            skip_phase(manifest, "langau-tool-comparison", "python3 is unavailable", out)
        else:
            run_phase(manifest, "langau-tool-comparison",
                      ["python3", str(comparison), str(args.e1_dir),
                       str(out / "results" / "langau-tool-comparison")], out)
    else:
        skip_phase(manifest, "langau-tool-comparison", "requested with --skip-tool-comparison", out)

    if not args.skip_stability:
        stability = STUDY / "run_fit_stability.py"
        if not fitter.is_file() or not args.cases.is_file():
            skip_phase(manifest, "fit-start-stability", "fitter or cases JSON unavailable", out)
        else:
            run_phase(manifest, "fit-start-stability",
                      ["python3", str(stability), "--cases", str(args.cases), "--fitter", str(fitter),
                       "--out", str(out / "results" / "fit-start-stability"), "--jobs", "2"], out)
    else:
        skip_phase(manifest, "fit-start-stability", "requested with --skip-stability", out)

    if not args.skip_campaign_audit:
        for index, campaign in enumerate(args.campaign, 1):
            campaign = campaign.expanduser().resolve()
            if not campaign.is_dir():
                skip_phase(manifest, f"campaign-{index}", f"missing directory: {campaign}", out)
                continue
            files = [p for p in campaign.rglob("*") if p.is_file()]
            record = {"path": str(campaign), "file_count": len(files),
                      "bytes": sum(p.stat().st_size for p in files),
                      "sha256": {str(p.relative_to(campaign)): sha256(p) for p in files
                                 if p.name in {"attempt.json", "provenance.json", "run.json", "manifest.json"}}}
            manifest.setdefault("campaign_audits", []).append(record)
            write_json(out / "manifest.json", manifest)
            print(f"[pass] campaign-{index}: {len(files)} files, {record['bytes']} bytes", flush=True)
    else:
        skip_phase(manifest, "campaign-audit", "requested with --skip-campaign-audit", out)

    compare_fullset = REPO / "examples/yall/compare_fullset.py"
    if args.calibration_work:
        if not compare_fullset.is_file():
            skip_phase(manifest, "calibration-comparison", f"missing utility: {compare_fullset}", out)
        else:
            for index, work in enumerate(args.calibration_work, 1):
                work = work.expanduser().resolve()
                match = re.search(r"(?:adaptive-)?fullset-([a-z])(\d+)-repro$", work.name, re.IGNORECASE)
                if not match:
                    skip_phase(manifest, f"calibration-{index}",
                               f"cannot infer FullSet name from {work}", out)
                    continue
                set_name = f"FullSet{match.group(1).upper()}_{match.group(2)}"
                run_phase(manifest, f"calibration-{set_name}",
                          ["python3", str(compare_fullset), "--set-name", set_name,
                           "--work", str(work), "--out", str(out / "results" / f"calibration-{set_name}"),
                           "--no-pdf"], out, cwd=REPO)
    else:
        skip_phase(manifest, "calibration-comparison",
                   "no --calibration-work was supplied; fit seeds and calibration outputs are not compared",
                   out)

    manifest["finished_utc"] = utc_now()
    failures = [p for p in manifest["phases"] if p.get("status") == "fail"]
    warnings = sum(p.get("status") == "warn" for p in manifest["phases"])
    manifest["summary"] = {"pass": sum(p.get("status") == "pass" for p in manifest["phases"]),
                            "warn": warnings, "fail": len(failures),
                            "overall": "FAIL" if failures else ("REVIEW" if warnings else "PASS")}
    write_json(out / "manifest.json", manifest)
    print("Manifest:", out / "manifest.json")
    print("Overall:", manifest["summary"]["overall"], "(no scientific acceptance is inferred)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
