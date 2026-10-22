#!/usr/bin/env python3
"""Build isolated, pinned PR #90 comparisons and run real ROOT plotting trials."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import statistics
import subprocess
import sys
import time

BASE = "92df3e48b84204dfacf0aa579893d379db5c5919"
PR = "3f33c280f056d3c65aeea50315667b08bc082441"
REPO = "https://github.com/paulnord/epic-lfhcal-tbana.git"
SOURCE_FILES = ["NewStructure/MultiCanvas.cc", "NewStructure/MultiCanvas.h"]


def capture(command: list[str], **kwargs) -> str:
    return subprocess.check_output(command, text=True, **kwargs).strip()


def logged(command: list[str], log: Path, **kwargs) -> None:
    print("+ " + shlex.join(command), flush=True)
    with log.open("a") as stream:
        stream.write("\n$ " + shlex.join(command) + "\n")
        stream.flush()
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def prerequisites() -> dict:
    missing = [name for name in ("git", "cmake", "root-config") if not shutil.which(name)]
    if missing:
        raise RuntimeError("Missing prerequisites: " + ", ".join(missing) +
                           ". Activate your existing ROOT environment first.")
    compiler = shlex.split(os.environ.get("CXX") or capture(["root-config", "--cxx"]))
    if not compiler or not shutil.which(compiler[0]):
        raise RuntimeError("No usable C++ compiler; set CXX to your ROOT-compatible compiler.")
    if len(compiler) != 1:
        raise RuntimeError("CXX must name one compiler executable, not a wrapper or flags.")
    return {
        "root_version": capture(["root-config", "--version"]),
        "root_prefix": capture(["root-config", "--prefix"]),
        "root_cflags": shlex.split(capture(["root-config", "--cflags"])),
        "root_libs": shlex.split(capture(["root-config", "--libs"])),
        "compiler": compiler,
        "compiler_version": capture(compiler + ["--version"]).splitlines()[0],
        "cmake_version": capture(["cmake", "--version"]).splitlines()[0],
        "platform": sys.platform,
    }


def checkout(repo: str, sha: str, target: Path, log: Path) -> None:
    # A fresh clone is deliberate: do not switch branches or add worktrees to
    # the user's existing checkout. --no-hardlinks also isolates local clones.
    logged(["git", "clone", "--no-checkout", "--no-hardlinks", "--", repo, str(target)], log)
    present = subprocess.run(["git", "-C", str(target), "cat-file", "-e", sha + "^{commit}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not present:
        logged(["git", "-C", str(target), "fetch", "--no-tags", REPO, sha], log)
    logged(["git", "-C", str(target), "checkout", "--detach", sha], log)
    actual = capture(["git", "-C", str(target), "rev-parse", "HEAD"])
    if actual != sha:
        raise RuntimeError(f"Checkout mismatch: expected {sha}, got {actual}")


def verify_scope(base: Path, pr: Path) -> None:
    # Exact text check ensures this benchmark is testing the intended change,
    # not a newer branch or an uncommitted local edit.
    for name in SOURCE_FILES:
        old = (base / name).read_text()
        new = (pr / name).read_text()
        spacing = "  " if name.endswith(".cc") else "   "
        before = f"PlotCorr2DLayer({spacing}std::map<int,TileSpectra> spectra, int option, \n"
        after = f"PlotCorr2DLayer({spacing}const std::map<int,TileSpectra>& spectra, int option,\n"
        if old.count(before) != 1 or old.replace(before, after) != new:
            raise RuntimeError(f"Unexpected changes in {name}; refusing an ambiguous comparison.")
    # Both commits must have identical trees except for these two files.
    def tree(path: Path) -> dict[str, str]:
        entries = capture(["git", "-C", str(path), "ls-tree", "-r", "HEAD"]).splitlines()
        return {line.split("\t", 1)[1]: line.split("\t", 1)[0] for line in entries}
    old_tree, new_tree = tree(base), tree(pr)
    changed = {p for p in set(old_tree) | set(new_tree) if old_tree.get(p) != new_tree.get(p)}
    if changed != set(SOURCE_FILES):
        raise RuntimeError(f"Unexpected diff paths: {sorted(changed)}")


def build(source: Path, build_dir: Path, driver: Path, env: dict, jobs: int, log: Path) -> Path:
    logged(["cmake", "-S", str(source / "NewStructure"), "-B", str(build_dir),
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + env["root_prefix"],
            "-DCMAKE_CXX_COMPILER=" + env["compiler"][0]], log)
    logged(["cmake", "--build", str(build_dir), "--target", "LFHCAL", "--parallel", str(jobs)], log)
    exe = build_dir / "plot_copy_bench"
    command = env["compiler"] + env["root_cflags"] + [
        "-O2", "-I" + str(source / "NewStructure"), str(driver),
        "-L" + str(build_dir), "-Wl,-rpath," + str(build_dir), "-lLFHCAL",
    ] + env["root_libs"] + ["-o", str(exe)]
    logged(command, log)
    return exe


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_environment(executable: Path) -> dict[str, str]:
    """Prevent a user's existing LFHCAL build from overriding the trial build."""
    environment = os.environ.copy()
    directory = str(executable.resolve().parent)
    for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        previous = environment.get(key)
        environment[key] = directory + (os.pathsep + previous if previous else "")
    return environment


def read_result(path: Path, wall: float, variant: str, trial: int) -> dict:
    result = json.loads((path / "result.json").read_text())
    for field in ("elapsed_seconds", "peak_rss_kib", "before_digest", "after_digest", "saved_digest",
                  "caller_unchanged", "round_trip_unchanged", "plot_file"):
        if field not in result:
            raise RuntimeError(f"Missing {field} in {path / 'result.json'}")
    if not result["caller_unchanged"] or result["before_digest"] != result["after_digest"]:
        raise RuntimeError(f"Plotting changed input histogram state: {path}")
    if not result["round_trip_unchanged"]:
        raise RuntimeError(f"Saved ROOT histogram state failed read-back verification: {path}")
    if result["elapsed_seconds"] <= 0 or result["peak_rss_kib"] <= 0:
        raise RuntimeError(f"Invalid timing/RSS measurement: {path}")
    plot = (path / result["plot_file"]).resolve()
    if not plot.is_relative_to(path.resolve()) or not plot.is_file() or plot.stat().st_size == 0:
        raise RuntimeError(f"Missing or invalid plot_file in {path}")
    result.update(variant=variant, trial=trial, process_wall_seconds=wall,
                  plot_sha256=sha256(plot), output_dir=str(path))
    return result


def summarize(results: list[dict]) -> dict:
    reference = results[0]
    semantic_fields = ["before_digest", "after_digest", "saved_digest"]
    semantics_equal = all(all(r.get(key) == reference.get(key) for key in semantic_fields) for r in results)
    png_equal = all(r["plot_sha256"] == reference["plot_sha256"] for r in results)
    stats = {}
    for variant in ("base", "pr90"):
        group = [r for r in results if r["variant"] == variant]
        stats[variant] = {
            "median_plot_seconds": statistics.median(r["elapsed_seconds"] for r in group),
            "median_process_peak_rss_mib": statistics.median(r["peak_rss_kib"] for r in group) / 1024.0,
            "min_plot_seconds": min(r["elapsed_seconds"] for r in group),
            "max_plot_seconds": max(r["elapsed_seconds"] for r in group),
        }
    seconds = stats["base"]["median_plot_seconds"]
    stats["plot_speedup_ratio"] = seconds / stats["pr90"]["median_plot_seconds"] if stats["pr90"]["median_plot_seconds"] else None
    stats["median_peak_rss_reduction_mib"] = stats["base"]["median_process_peak_rss_mib"] - stats["pr90"]["median_process_peak_rss_mib"]
    return {"semantic_digests_equal": semantics_equal, "png_bytes_equal": png_equal,
            "stats": stats, "trials": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=REPO, help="Source repository URL or local checkout (never modified).")
    parser.add_argument("--out", type=Path, help="New directory for isolated clones, builds and results; must not exist.")
    parser.add_argument("--cells", type=int, default=32, help="Dense TileSpectra objects in the map (default: 32).")
    parser.add_argument("--iterations", type=int, default=5, help="Timed real plotting calls per process (default: 5).")
    parser.add_argument("--warmup", type=int, default=1, help="Untimed plotting calls per process (default: 1).")
    parser.add_argument("--trials", type=int, default=5, help="Separate process trials per version (default: 5).")
    parser.add_argument("--jobs", type=int, default=2, help="Parallel build jobs (default: 2).")
    parser.add_argument("--check-only", action="store_true", help="Check prerequisites without cloning/building/running.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without checking dependencies or writing files.")
    args = parser.parse_args(argv)
    if min(args.cells, args.iterations, args.trials, args.jobs) < 1 or args.warmup < 0:
        parser.error("cells, iterations, trials and jobs must be positive; warmup must be nonnegative")
    if args.cells > 128:
        parser.error("cells above 128 can exceed several GiB; edit the explicit guard only after checking available memory")
    if args.dry_run:
        print(json.dumps({"base": BASE, "pr90": PR, "source": args.repo,
                          "cells": args.cells, "iterations": args.iterations,
                          "warmup": args.warmup, "trials_per_version": args.trials,
                          "action": "fresh clones; build LFHCAL; compile ROOT driver; alternating separate-process trials"}, indent=2))
        return 0
    info = prerequisites()
    print(json.dumps(info, indent=2))
    if args.check_only:
        return 0
    driver = Path(__file__).resolve().with_name("plot_copy_bench.cc")
    if not driver.is_file():
        raise RuntimeError("Keep plot_copy_bench.cc next to this script.")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = (args.out or Path("pr90-benchmark-" + stamp)).resolve()
    out.mkdir(parents=True, exist_ok=False)
    info.update(base=BASE, pr90=PR, driver_sha256=sha256(driver), args=vars(args) | {"out": str(out)})
    (out / "environment.json").write_text(json.dumps(info, indent=2, default=str) + "\n")
    sources = {label: out / (label + "-source") for label in ("base", "pr90")}
    for label, sha in (("base", BASE), ("pr90", PR)):
        checkout(args.repo, sha, sources[label], out / (label + "-build.log"))
    verify_scope(sources["base"], sources["pr90"])
    executables = {
        label: build(sources[label], out / (label + "-build"), driver, info, args.jobs,
                     out / (label + "-build.log")) for label in ("base", "pr90")
    }
    results = []
    for trial in range(1, args.trials + 1):
        for label in (("base", "pr90") if trial % 2 else ("pr90", "base")):
            run_dir = out / f"trial-{trial:02d}-{label}"
            run_dir.mkdir()
            command = [str(executables[label]), str(run_dir), str(args.cells), str(args.iterations), str(args.warmup)]
            started = time.monotonic()
            environment = runtime_environment(executables[label])
            logged(command, run_dir / "run.log", cwd=str(out / (label + "-build")), env=environment)
            result = read_result(run_dir, time.monotonic() - started, label, trial)
            result["runtime_library_paths"] = {key: environment[key] for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")}
            results.append(result)
            print(f"{label} trial {trial}: {result['elapsed_seconds']:.3f} s plotting, "
                  f"{result['peak_rss_kib'] / 1024:.1f} MiB process peak RSS", flush=True)
    summary = summarize(results)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (out / "trials.csv").open("w", newline="") as stream:
        fields = ["variant", "trial", "elapsed_seconds", "peak_rss_kib", "process_wall_seconds", "plot_sha256"]
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps({k: v for k, v in summary.items() if k != "trials"}, indent=2))
    print(f"Results and logs: {out}")
    if not summary["semantic_digests_equal"]:
        print("FAIL: semantic snapshot differences between versions/trials.", file=sys.stderr)
        return 2
    if not summary["png_bytes_equal"]:
        print("REVIEW: PNG bytes differ. Compare the images; metadata differences alone are not proof of a visual regression.", file=sys.stderr)
        return 3
    print("PASS: caller state, saved-state digests, and PNG bytes match across all trials.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
