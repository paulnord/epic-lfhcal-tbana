#!/usr/bin/env python3
"""Collect two completed E1 campaigns without their large event trees."""

import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile


def campaign_inputs(campaign):
    campaign = Path(campaign).resolve()
    if campaign.exists() and not campaign.is_dir():
        raise ValueError(f"Campaign path is not a directory: {campaign}")
    if not campaign.is_dir():
        # The campaigns directory is user-named. Recover a misspelled parent
        # only when the exact campaign name has one match in the same work.
        work = campaign.parent.parent
        matches = sorted({(parent / campaign.name).resolve()
                          for parent in work.iterdir()
                          if parent.is_dir() and not parent.is_symlink()
                          and (parent / campaign.name).is_dir()
                          and not (parent / campaign.name).is_symlink()}) if work.is_dir() else []
        if len(matches) != 1:
            detail = "Multiple matching campaigns" if matches else "Campaign directory not found"
            raise ValueError(f"{detail}: {campaign}")
        campaign = matches[0]
        print(f"Using existing campaign: {campaign}")
    work = campaign.parent.parent
    results = work / "fullset-e1-repro"
    required = [results / "skim-check/selection.json",
                results / "final/calib_Final_Muon_FullSetE_1_calib.txt"]
    for stage in range(1, 6):
        directory = results / f"refine{stage}"
        if not list(directory.glob("*_Hists.root")):
            raise ValueError(f"Missing histograms: {directory}")
        if not list(directory.glob("*_calib.txt")):
            raise ValueError(f"Missing calibration text: {directory}")
    for path in required:
        if not path.is_file():
            raise ValueError(f"Missing required result: {path}")
    files = []
    for name in ("after-mip-setup.json", "host-setup.json"):
        path = work / name
        if path.is_file() and not path.is_symlink():
            files.append((path, Path(name)))
    for directory in (campaign, results):
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(work)
            if "plots" in relative.parts:
                continue
            if path.suffix.lower() == ".root" and not path.name.endswith("_Hists.root"):
                continue
            files.append((path, relative))
    return campaign, files


def checkout_info(repo):
    lines = [f"Packaging checkout: {repo}\n",
             "This records the current checkout; campaign logs describe the jobs.\n"]
    for args in (("log", "-1", "--format=%H %s"), ("status", "--short"),
                 ("diff", "HEAD")):
        lines.append(subprocess.check_output(
            ["git", "-C", str(repo), *args], text=True))
    return "\n".join(lines)


def collect(fixed_x, muon_m, repo):
    x, xfiles = campaign_inputs(fixed_x)
    m, mfiles = campaign_inputs(muon_m)
    if x == m:
        raise ValueError("The two campaign paths must be different")
    provenance = checkout_info(repo)
    # A fresh sibling directory keeps packaging outside both input work areas.
    out = Path(tempfile.mkdtemp(prefix="e1-comparison-", dir=x.parent.parent.parent))
    archive = out / "E1-X-vs-M.tgz"
    temporary = out / "E1-X-vs-M.tgz.partial"
    count = 0
    with tarfile.open(temporary, "w:gz") as tar:
        text = provenance + f"\nfixed-X campaign: {x}\nmuon-M campaign: {m}\n"
        data = text.encode()
        info = tarfile.TarInfo("checkout.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        for label, files in (("fixed-X", xfiles), ("muon-M", mfiles)):
            for source, relative in files:
                tar.add(source, arcname=str(Path(label) / relative), recursive=False)
                count += 1
    temporary.rename(archive)
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    checksum = Path(str(archive) + ".sha256")
    checksum.write_text(f"{digest.hexdigest()}  {archive.name}\n")
    print(f"Packed {count} input files; {archive.stat().st_size / 1024**2:.1f} MiB")
    print("Transfer these two files:")
    print(archive)
    print(checksum)
    return archive, checksum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixed_x", help="Corrected -X campaign directory ($C)")
    parser.add_argument("muon_m", help="Muon-only -M campaign directory ($CM)")
    args = parser.parse_args()
    try:
        collect(args.fixed_x, args.muon_m, Path(__file__).resolve().parents[2])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Collection failed: {error}\n")


if __name__ == "__main__":
    main()
