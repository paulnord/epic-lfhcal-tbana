#!/usr/bin/env python3
"""Prepare the R5 replay from the four environment variables used by Yallfile.

No compilation, job submission, refitting, or edits to the reference results.
Run after building the separate plotting checkout. Compatible with Python 3.6+.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(path):
    require(path.is_file() and path.stat().st_size > 0, "Missing/empty input: " + str(path))


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest() + "  " + str(path) + "\n"


def save_unchanged_or_new(path, text):
    if path.exists():
        require(path.read_text() == text, "Existing setup differs; choose a fresh PLOT_WORK: " + str(path))
    else:
        path.write_text(text)


def main():
    paths = {}
    for name in ("PS_REFERENCE", "PLOT_WORK", "PLOT_SOURCE", "EIC_SHELL"):
        require(bool(os.environ.get(name)), "Set " + name + " first.")
        paths[name] = Path(os.environ[name]).expanduser().resolve()
    ref, work, source, shell = (paths[n] for n in
                               ("PS_REFERENCE", "PLOT_WORK", "PLOT_SOURCE", "EIC_SHELL"))
    require(ref.is_dir(), "Reference directory missing: " + str(ref))
    require(work != ref and ref not in work.parents and work not in ref.parents,
            "PLOT_WORK and PS_REFERENCE must be separate, non-overlapping directories.")
    require(shell.is_file() and os.access(str(shell), os.X_OK), "EIC shell is not executable: " + str(shell))
    recipe = source / "examples/yall/ps-replot-r5/Yallfile"
    text = recipe.read_text()
    rows = text.split("@table sets psset sample:\n", 1)[1].split("\n\n", 1)[0]
    pairs = [line.split() for line in rows.splitlines() if line.strip()]
    require(len(pairs) == 17 and all(len(row) == 2 for row in pairs), "Expected 17 set/sample pairs.")
    build = source / "NewStructure/build"
    payload = [build / "DataPrep", build / "libLFHCAL.so"]
    for path in payload:
        nonempty(path)
    require(os.access(str(payload[0]), os.X_OK), "DataPrep is not executable.")
    # This replay targets the original Legacy fitter, not an activated adaptive patch.
    legacy = subprocess.check_output(["git", "hash-object", str(source / "NewStructure/TileSpectra.cc")],
                                     universal_newlines=True).strip()
    require(legacy == "594403ddae0b318c013e7ea7145087b4fdcf7188", "Expected the unchanged Legacy fitter.")
    nonempty(source / "NewStructure/FitCurveDrawing.h")
    nonempty(source / "configs/TB2026/DataTakingDB_TBPST10_202604_HGCROC.csv")
    for psset, sample in pairs:
        nonempty(ref / psset / "select" / ("rawHGCROC_mipTrigg_wPedwMuon_wBC_" + sample + ".root"))
        nonempty(ref / psset / "refine4" / ("rawHGCROC_wPedwMuon_wBC_Imp4R_" + sample + "_calib.txt"))
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                     universal_newlines=True).strip()
    record = json.dumps(dict(reference=str(ref), source=str(source), source_commit=commit,
                             method="legacy", replay="R5", earlier_plots="reused unchanged"), indent=2) + "\n"
    work.mkdir(parents=True, exist_ok=True)
    save_unchanged_or_new(work / "preparation.json", record)
    save_unchanged_or_new(work / "build.sha256", "".join(checksum(p) for p in payload))
    save_unchanged_or_new(work / "Yallfile", text)
    (work / "campaigns").mkdir(exist_ok=True)
    for psset, sample in pairs:
        (work / psset / "final").mkdir(parents=True, exist_ok=True)
        plots = work / psset / "plots"
        # The sample directory is a declared task output. Even an empty leaf
        # would prevent yall-run start; DataPrep creates it when plotting.
        (plots / "refine5").mkdir(parents=True, exist_ok=True)
        for stage in ("pedestal", "transfer", "mip", "refine1", "refine2", "refine3", "refine4"):
            old, link = ref / psset / "plots" / stage, plots / stage
            if old.is_dir():
                if link.exists() or link.is_symlink():
                    require(link.is_symlink() and link.resolve() == old.resolve(), "Conflicting plot path: " + str(link))
                else:
                    link.symlink_to(old, target_is_directory=True)
    print("Prepared 17 R5 replay jobs: " + str(work / "Yallfile"))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
