#!/usr/bin/env python3
"""Package existing HV-scan histograms and calibration text; no ROOT required.

Python 3.6+ standard library only. This reads the campaign's refine2 histograms,
their refine1 seed calibration, and their refine2 result calibration. It never
opens event ROOT files or runs event processing, histogram filling, or fitting.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tarfile
import tempfile


# examples/yall/hvscan-repro/Yallfile and README.md.
RUN_HV = {194: 44.0, 195: 43.0, 196: 43.5, 197: 44.5, 198: 45.0,
          199: 45.5, 200: 46.0, 201: 42.0, 202: 42.5}


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fingerprint(path):
    digest = hashlib.sha256()
    size = 0
    with open(str(path), "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"size_bytes": size, "sha256": digest.hexdigest()}


def required_inputs(work, runs):
    if not runs or len(set(runs)) != len(runs):
        raise ValueError("runs must be a nonempty list without duplicates")
    unknown = sorted(set(runs) - set(RUN_HV))
    if unknown:
        raise ValueError("unknown HV-scan runs: {}".format(unknown))
    records = []
    for run in sorted(runs):
        specifications = [
            ("refine2", "histograms", "rawHGCROC_wPedwMuon_wBC_Imp2R_{}_Hists.root"),
            ("refine1", "seed_calibration", "rawHGCROC_wPedwMuon_wBC_ImpR_{}_calib.txt"),
            ("refine2", "result_calibration", "rawHGCROC_wPedwMuon_wBC_Imp2R_{}_calib.txt"),
        ]
        for stage, kind, template in specifications:
            relative = str(Path(stage) / template.format(run))
            records.append({"source_absolute": str((work / relative).resolve()),
                            "relative_path": relative, "run": run,
                            "hv_volts": RUN_HV[run], "stage": stage, "kind": kind})
    return records


def copy_exclusive(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(str(source), "rb") as src, open(str(destination), "xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)


def write_json_exclusive(path, document):
    with open(str(path), "x") as out:
        json.dump(document, out, indent=2, sort_keys=True)
        out.write("\n")


def verify_unchanged(path, expected, description):
    actual = fingerprint(path)
    if any(actual[key] != expected[key] for key in ("size_bytes", "sha256")):
        raise RuntimeError("{} changed: {}".format(description, path))


def collect(work, out_parent, runs=None):
    """Return (fresh directory, archive, checksum); failures never omit runs."""
    started = utc_now()
    work = Path(work).resolve()
    out_parent = Path(out_parent).resolve()
    runs = sorted(RUN_HV) if runs is None else list(runs)
    if not work.is_dir():
        raise ValueError("campaign directory does not exist: {}".format(work))
    if not out_parent.is_dir():
        raise ValueError("output parent must already exist: {}".format(out_parent))
    records = required_inputs(work, runs)
    missing = [record["source_absolute"] for record in records
               if not Path(record["source_absolute"]).is_file()]
    if missing:
        raise ValueError("missing required inputs; no bundle created:\n" + "\n".join(missing))

    # Read all required inputs before creating output, so missing or unreadable
    # inputs cannot look like a successful smaller population.
    for record in records:
        record.update(fingerprint(record["source_absolute"]))
    empty = [record["source_absolute"] for record in records if record["size_bytes"] == 0]
    if empty:
        raise ValueError("empty required inputs; no bundle created:\n" + "\n".join(empty))
    code = {"source_absolute": str(Path(__file__).resolve()),
            "relative_path": "collector/collect_hv_histograms.py"}
    code.update(fingerprint(code["source_absolute"]))

    output = Path(tempfile.mkdtemp(prefix="hv-histograms-", dir=str(out_parent)))
    archive = Path(str(output) + ".tgz")
    partial = Path(str(archive) + ".partial")
    checksum = Path(str(archive) + ".sha256")
    try:
        for record in records + [code]:
            destination = output / record["relative_path"]
            copy_exclusive(record["source_absolute"], destination)
            verify_unchanged(destination, record, "copied bytes")
        for record in records + [code]:
            verify_unchanged(record["source_absolute"], record, "source")
        manifest = {
            "schema_version": 1,
            "status": "complete",
            "description": "Existing full refine2 histogram files and refine1/refine2 calibration text; no refilling or fitting",
            "source_work_absolute": str(work),
            "hostname": socket.gethostname(),
            "started_utc": started,
            "finished_utc": utc_now(),
            "runs": [{"run": run, "hv_volts": RUN_HV[run]} for run in sorted(runs)],
            "histogram_stage": "refine2",
            "file_count": len(records),
            "files": records,
            "collector": code,
        }
        write_json_exclusive(output / "manifest.json", manifest)
        with open(str(partial), "xb") as raw:
            with tarfile.open(fileobj=raw, mode="w:gz") as bundle:
                for relative in ([record["relative_path"] for record in records] +
                                 [code["relative_path"], "manifest.json"]):
                    bundle.add(str(output / relative), arcname=relative, recursive=False)
        # Check that inputs stayed unchanged through the complete archive write.
        for record in records + [code]:
            verify_unchanged(record["source_absolute"], record, "source")
            verify_unchanged(output / record["relative_path"], record, "staged bytes")
        digest = fingerprint(partial)["sha256"]
        # Hard-link publication is atomic and refuses an existing destination.
        os.link(str(partial), str(archive))
        partial.unlink()
        with open(str(checksum), "x") as out:
            out.write("{}  {}\n".format(digest, archive.name))
    except Exception as error:
        failure = {"status": "failed", "finished_utc": utc_now(), "error": str(error)}
        write_json_exclusive(output / "failure.json", failure)
        raise RuntimeError("collection failed; partial outputs preserved in {}: {}".format(output, error))
    return output, archive, checksum


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, help="existing hvscan-repro campaign directory")
    parser.add_argument("--out-parent", required=True, help="existing parent for a fresh bundle directory")
    parser.add_argument("--runs", type=int, nargs="+", choices=sorted(RUN_HV),
                        default=sorted(RUN_HV), help="runs to include (default: all nine, 194 through 202)")
    args = parser.parse_args(argv)
    try:
        output, archive, checksum = collect(args.work, args.out_parent, args.runs)
    except (OSError, ValueError, RuntimeError) as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        return 1
    print("Bundle: {}".format(output))
    print("Runs: {}; source files: {}".format(", ".join(map(str, sorted(args.runs))), len(args.runs) * 3))
    print("Source and copied-file SHA256 checks passed; no ROOT processing performed.")
    print("Transfer these two files to the Mac:\n{}\n{}".format(archive, checksum))
    return 0


if __name__ == "__main__":
    sys.exit(main())
