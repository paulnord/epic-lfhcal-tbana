#!/usr/bin/env python3
"""Compare pinned PR #90 HGCROCStudy builds on the same local ROOT input."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import signal
import statistics
import subprocess
import sys
import time

from run_pr90_benchmark import BASE, PR, REPO, checkout, logged, prerequisites, runtime_environment, sha256, verify_scope

# Deliberately narrow: this is a waveform benchmark, not a shell/job runner.
FILE_OPTIONS = {"-i", "-r", "-C", "-B", "-k", "-t", "-l"}
NUMBER_OPTIONS = {"-d", "-E", "-L", "-q", "-Q", "-s", "-c"}
VALUE_OPTIONS = FILE_OPTIONS | NUMBER_OPTIONS | {"-o", "-O", "-F"}
SAFE_OUTPUT = re.compile(r"/[A-Za-z0-9_./-]+\Z")


def safe_output_path(path: Path) -> Path:
    path = path.resolve()
    # The pinned upstream analysis uses unquoted gSystem->Exec("mkdir -p "+path).
    # Restrict output paths rather than changing either version under comparison.
    if not SAFE_OUTPUT.fullmatch(str(path)):
        raise RuntimeError("Output path must contain only ASCII letters, digits, /, _, ., and -; "
                           "the pinned analysis uses an unquoted shell mkdir internally.")
    if ".root" in str(path):
        raise RuntimeError("Output directory cannot contain '.root': the pinned analysis replaces every "
                           "'.root' substring in the full output filename with '_Hists.root'.")
    return path


def load_config(path: Path, check_files: bool = True) -> dict:
    return validate_config(json.loads(path.read_text()), check_files=check_files)


def validate_config(config: dict, check_files: bool = True) -> dict:
    if not isinstance(config, dict) or set(config) != {"inputs", "argv"}:
        raise RuntimeError("Config must contain exactly 'inputs' and 'argv'.")
    inputs = config["inputs"]
    if not isinstance(inputs, dict) or not inputs:
        raise RuntimeError("inputs must map placeholder names to absolute local file paths.")
    for key, value in inputs.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key) or key in {"exe", "output"}:
            raise RuntimeError(f"Invalid or reserved input placeholder: {key}")
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise RuntimeError(f"Input {key} must be an absolute local file path.")
        if "\x00" in value:
            raise RuntimeError(f"Input {key} contains a NUL character.")
        resolved = Path(value).resolve()
        if check_files and not resolved.is_file():
            raise RuntimeError(f"Input {key} is not a regular file: {resolved}")
        inputs[key] = str(resolved)
    argv = config["argv"]
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise RuntimeError("argv must be a nonempty JSON array of strings, not a shell command.")
    if argv[0] != "{exe}":
        raise RuntimeError("argv must start with '{exe}'.")
    options = {}
    used_inputs = set()
    index = 1
    while index < len(argv):
        flag = argv[index]
        if flag in options or flag not in VALUE_OPTIONS | {"-w"}:
            raise RuntimeError(f"Duplicate or unsupported option: {flag}; use separate option/value tokens.")
        if flag == "-w":
            options[flag] = True
            index += 1
            continue
        if index + 1 == len(argv):
            raise RuntimeError(f"Missing value for {flag}")
        value = argv[index + 1]
        options[flag] = value
        if flag in FILE_OPTIONS:
            if value not in {"{" + key + "}" for key in inputs}:
                raise RuntimeError(f"{flag} must use an exact placeholder declared in inputs.")
            used_inputs.add(value[1:-1])
        elif flag in NUMBER_OPTIONS:
            if not re.fullmatch(r"-?[0-9]+", value):
                raise RuntimeError(f"{flag} needs an integer.")
            if flag in {"-L", "-q", "-Q"} and int(value) < 1:
                raise RuntimeError(f"{flag} must be positive when provided.")
        elif flag == "-o" and value != "{output}/analysis.root":
            raise RuntimeError("-o must be '{output}/analysis.root'.")
        elif flag == "-O" and value != "{output}/plots":
            raise RuntimeError("-O must be '{output}/plots'.")
        elif flag == "-F" and value not in {"png", "pdf"}:
            raise RuntimeError("-F must be png or pdf.")
        index += 2
    for flag in ("-w", "-i", "-r", "-o", "-O", "-F"):
        if flag not in options:
            raise RuntimeError(f"Missing required option: {flag}")
    if used_inputs != set(inputs):
        raise RuntimeError("Every declared input must be used in argv.")
    return config


def waveform_config(input_file: Path, runlist: Path, calibration: Path | None,
                    max_events: int | None) -> dict:
    inputs = {"input": str(input_file.resolve()), "runlist": str(runlist.resolve())}
    argv = ["{exe}", "-w", "-i", "{input}", "-r", "{runlist}",
            "-o", "{output}/analysis.root", "-O", "{output}/plots", "-F", "png"]
    if calibration:
        inputs["calibration"] = str(calibration.resolve())
        argv.extend(["-C", "{calibration}"])
    if max_events is not None:
        argv.extend(["-L", str(max_events)])
    return {"inputs": inputs, "argv": argv}


def command_for(config: dict, executable: Path, output: Path) -> list[str]:
    substitutions = {"{exe}": str(executable), **{"{" + k + "}": v for k, v in config["inputs"].items()},
                     "{output}/analysis.root": str(output / "analysis.root"),
                     "{output}/plots": str(output / "plots")}
    # Exact-token substitution, not eval, a shell, or arbitrary format expressions.
    return [substitutions.get(token, token) for token in config["argv"]]


def input_snapshot(inputs: dict, hash_contents: bool = False) -> dict:
    result = {}
    for name, value in inputs.items():
        path = Path(value)
        stat = path.stat()
        result[name] = {"path": value, "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                        "device": stat.st_dev, "inode": stat.st_ino}
        if hash_contents:
            result[name]["sha256"] = sha256(path)
    return result


def build_analysis(source: Path, build_dir: Path, env: dict, jobs: int, log: Path) -> Path:
    logged(["cmake", "-S", str(source / "NewStructure"), "-B", str(build_dir),
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + env["root_prefix"],
            "-DCMAKE_CXX_COMPILER=" + env["compiler"][0]], log)
    logged(["cmake", "--build", str(build_dir), "--target", "HGCROCStudy", "--parallel", str(jobs)], log)
    executable = build_dir / "HGCROCStudy"
    if not executable.is_file():
        raise RuntimeError(f"Build did not produce {executable}")
    return executable


def measured_process(command: list[str], cwd: Path, log: Path) -> dict:
    """Measure only this child, not cumulative RUSAGE_CHILDREN across trials."""
    if not hasattr(os, "wait4") or sys.platform not in {"linux", "darwin"}:
        raise RuntimeError("Per-process measurement requires Linux or macOS with os.wait4.")
    print("+ " + shlex.join(command), flush=True)
    child_env = runtime_environment(Path(command[0]))
    with log.open("x") as stream:
        stream.write("$ " + shlex.join(command) + "\n")
        stream.flush()
        started = time.monotonic()
        process = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True, env=child_env)
        try:
            while True:
                try:
                    _, status, usage = os.wait4(process.pid, 0)
                    break
                except InterruptedError:
                    continue
        except BaseException:
            # Do not leave the expensive analysis running after Ctrl-C.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _, status, _ = os.wait4(process.pid, 0)
            process.returncode = os.waitstatus_to_exitcode(status)
            raise
        elapsed = time.monotonic() - started
        process.returncode = os.waitstatus_to_exitcode(status)
    return {"elapsed_seconds": elapsed, "peak_rss_kib": usage.ru_maxrss / (1024 if sys.platform == "darwin" else 1),
            "user_cpu_seconds": usage.ru_utime, "system_cpu_seconds": usage.ru_stime,
            "returncode": process.returncode,
            "library_search_paths": {key: child_env.get(key, "") for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")}}


def inspect_outputs(output: Path, extension: str) -> dict:
    histograms = output / "analysis_Hists.root"
    if not histograms.is_file() or histograms.stat().st_size == 0:
        raise RuntimeError(f"Missing/empty waveform histogram output: {histograms}")
    plots = sorted((output / "plots").rglob("*." + extension))
    if not any(p.name.startswith("Waveform_") for p in plots):
        raise RuntimeError("No Waveform_* plots were produced; check detector support, masking and run configuration.")
    if any(p.stat().st_size == 0 for p in plots):
        raise RuntimeError(f"Empty plot in {output}")
    return {"histogram_file": str(histograms), "histogram_file_bytes": histograms.stat().st_size,
            "plot_sha256": {str(p.relative_to(output / "plots")): sha256(p) for p in plots}}


def summarize(results: list[dict]) -> dict:
    stats = {}
    for label in ("base", "pr90"):
        group = [r for r in results if r["variant"] == label]
        stats[label] = {"median_elapsed_seconds": statistics.median(r["elapsed_seconds"] for r in group),
                        "min_elapsed_seconds": min(r["elapsed_seconds"] for r in group),
                        "max_elapsed_seconds": max(r["elapsed_seconds"] for r in group),
                        "median_peak_rss_mib": statistics.median(r["peak_rss_kib"] for r in group) / 1024}
    stats["end_to_end_speedup_ratio"] = stats["base"]["median_elapsed_seconds"] / stats["pr90"]["median_elapsed_seconds"]
    stats["median_peak_rss_reduction_mib"] = stats["base"]["median_peak_rss_mib"] - stats["pr90"]["median_peak_rss_mib"]
    reference = results[0]["plot_sha256"]
    return {"stats": stats, "plot_files_equal": all(set(r["plot_sha256"]) == set(reference) for r in results),
            "plot_bytes_equal": all(r["plot_sha256"] == reference for r in results),
            "root_histogram_semantics_checked": False, "trials": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Advanced HGCROCStudy JSON config instead of direct input options.")
    parser.add_argument("--input", type=Path, help="Converted HGCROC ROOT data file.")
    parser.add_argument("--runlist", type=Path, help="Run list containing this data file's run number.")
    parser.add_argument("--calibration", type=Path, help="Optional external ROOT calibration file (-C).")
    event_limit = parser.add_mutually_exclusive_group()
    event_limit.add_argument("--max-events", type=int, help="Event limit per process (direct CLI default: 1000).")
    event_limit.add_argument("--all-events", action="store_true", help="Explicitly process the full input, omitting -L.")
    parser.add_argument("--repo", default=REPO, help="Repository URL or local checkout; never modified.")
    parser.add_argument("--out", type=Path, help="New output directory; must not exist. No spaces/shell punctuation.")
    parser.add_argument("--trials", type=int, default=3, help="Separate processes per version (default: 3).")
    parser.add_argument("--jobs", type=int, default=2, help="Parallel build jobs (default: 2).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-only", action="store_true", help="Check dependencies; optionally validate --config inputs.")
    mode.add_argument("--dry-run", action="store_true", help="Validate config shape and show commands; do not write or execute.")
    args = parser.parse_args(argv)
    if args.trials < 1 or args.jobs < 1:
        parser.error("trials and jobs must be positive")
    direct_options = args.input or args.runlist or args.calibration or args.max_events is not None or args.all_events
    if args.config and direct_options:
        parser.error("--config cannot be combined with direct input or event-limit options")
    if args.max_events is not None and args.max_events < 1:
        parser.error("--max-events must be positive; use --all-events for a full-file run")
    if args.config:
        config = load_config(args.config, check_files=not args.dry_run)
    elif args.input and args.runlist:
        limit = None if args.all_events else (args.max_events or 1000)
        config = validate_config(waveform_config(args.input, args.runlist, args.calibration, limit),
                                 check_files=not args.dry_run)
    elif args.check_only and not direct_options:
        config = None
    else:
        parser.error("provide --input and --runlist, or --config")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = safe_output_path(args.out or Path("pr90-real-data-" + stamp))
    if args.dry_run:
        print(json.dumps({"base": BASE, "pr90": PR, "source": args.repo,
                          "trials_per_version": args.trials, "inputs": config["inputs"],
                          "example_command": command_for(config, out / "base-build/HGCROCStudy", out / "trial-01-base"),
                          "measurement": "end-to-end wall time and wait4 child peak RSS; histogram semantics not checked"}, indent=2))
        return 0
    if not hasattr(os, "wait4") or sys.platform not in {"linux", "darwin"}:
        raise RuntimeError("This benchmark needs Linux or macOS with os.wait4.")
    info = dict(prerequisites())
    print(json.dumps(info, indent=2))
    if args.check_only:
        return 0
    if out.exists():
        raise RuntimeError(f"Output directory already exists; choose a new --out: {out}")
    # Input hashing is outside all timed trials; it will warm filesystem caches.
    original = input_snapshot(config["inputs"], hash_contents=True)
    original_stat = {k: {f: v for f, v in record.items() if f != "sha256"} for k, record in original.items()}
    out.mkdir(parents=True, exist_ok=False)
    info.update(base=BASE, pr90=PR, config=config, input_snapshot_before=original,
                args=vars(args) | {"out": str(out)}, runner_sha256=sha256(Path(__file__)),
                measurement="whole analysis process; no plotting-only timer; wait4 child ru_maxrss",
                root_histogram_semantics_checked=False)
    (out / "environment.json").write_text(json.dumps(info, indent=2, default=str) + "\n")
    sources = {label: out / (label + "-source") for label in ("base", "pr90")}
    for label, commit in (("base", BASE), ("pr90", PR)):
        checkout(args.repo, commit, sources[label], out / (label + "-build.log"))
    verify_scope(sources["base"], sources["pr90"])
    executables = {label: build_analysis(sources[label], out / (label + "-build"), info,
                                        args.jobs, out / (label + "-build.log")) for label in sources}
    results = []
    extension = config["argv"][config["argv"].index("-F") + 1]
    for trial in range(1, args.trials + 1):
        for label in (("base", "pr90") if trial % 2 else ("pr90", "base")):
            if input_snapshot(config["inputs"]) != original_stat:
                raise RuntimeError("An input changed before a trial; refusing a non-identical-input comparison.")
            run_dir = out / f"trial-{trial:02d}-{label}"
            run_dir.mkdir(exist_ok=False)
            command = command_for(config, executables[label], run_dir)
            result = measured_process(command, run_dir, run_dir / "run.log")
            result.update(variant=label, trial=trial, command=command, output_dir=str(run_dir))
            (run_dir / "measurement.json").write_text(json.dumps(result, indent=2) + "\n")
            if result["returncode"] != 0:
                raise RuntimeError(f"{label} trial {trial} exited {result['returncode']}; see {run_dir / 'run.log'}")
            result.update(inspect_outputs(run_dir, extension))
            results.append(result)
            (out / "completed_trials.json").write_text(json.dumps(results, indent=2) + "\n")
            print(f"{label} trial {trial}: {result['elapsed_seconds']:.3f} s total, "
                  f"{result['peak_rss_kib'] / 1024:.1f} MiB peak RSS", flush=True)
    after = input_snapshot(config["inputs"], hash_contents=True)
    (out / "input_snapshot_after.json").write_text(json.dumps(after, indent=2) + "\n")
    if after != original:
        raise RuntimeError("An input changed during the comparison; timing results are not comparable.")
    summary = summarize(results)
    summary["input_files_unchanged_on_disk"] = True
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (out / "trials.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, ["variant", "trial", "elapsed_seconds", "peak_rss_kib", "user_cpu_seconds", "system_cpu_seconds"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps({k: v for k, v in summary.items() if k != "trials"}, indent=2))
    print(f"Timing comparison complete: {out}")
    print("ROOT histogram semantics were NOT checked. See REAL_DATA.md for interpretation and output review.")
    if not summary["plot_bytes_equal"]:
        print("REVIEW: plot bytes differ; compare plots. PDF metadata may differ without a visual change.")
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
