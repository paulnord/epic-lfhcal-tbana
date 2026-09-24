#!/usr/bin/env python3
"""Compare archived and replayed E1 refine5 calibrations and saved HG fits."""

import argparse
import json
from pathlib import Path
import re
from statistics import median


FIT_NAME = re.compile(r"fmipmipTriggHGCellID(\d+)$")


def calibration(path: Path) -> dict[int, dict[str, float]]:
    cells = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 18 or not fields[0].isdigit():
            continue
        cell = int(fields[0])
        if cell in cells:
            raise ValueError(f"duplicate calibration cell {cell} in {path}")
        cells[cell] = {"mip_scale_h": float(fields[9]), "mip_width_h": float(fields[10])}
    if len(cells) != 384:
        raise ValueError(f"expected 384 E1 calibration records in {path}; found {len(cells)}")
    return cells


def fits(path: Path) -> dict[int, dict[str, float]]:
    import ROOT

    ROOT.gROOT.SetBatch(True)
    root_file = ROOT.TFile.Open(str(path))
    if not root_file or root_file.IsZombie():
        raise ValueError(f"cannot open ROOT histogram file: {path}")
    directory = root_file.Get("IndividualCellsTrigg")
    if not directory:
        raise ValueError(f"IndividualCellsTrigg directory is absent: {path}")
    result = {}
    for key in directory.GetListOfKeys():
        match = FIT_NAME.fullmatch(key.GetName())
        if not match or key.GetClassName() != "TF1":
            continue
        cell = int(match.group(1))
        if cell in result:
            continue  # ROOT may list earlier cycles of the same fit.
        fit = directory.Get(key.GetName())  # Retrieves the newest cycle.
        if fit.GetNpar() < 4:
            continue
        ndf = int(fit.GetNDF())
        result[cell] = {
            "landau_width": fit.GetParameter(0), "mpv": fit.GetParameter(1),
            "area": fit.GetParameter(2), "gaussian_sigma": fit.GetParameter(3),
            "chi2": fit.GetChisquare(), "ndf": ndf,
            "chi2_ndf": fit.GetChisquare() / ndf if ndf > 0 else None,
        }
    root_file.Close()
    if not result:
        raise ValueError(f"no saved high-gain MIP fits in {path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline-calib", "candidate-calib", "baseline-hists", "candidate-hists", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    baseline_calib = calibration(args.baseline_calib)
    candidate_calib = calibration(args.candidate_calib)
    if baseline_calib.keys() != candidate_calib.keys():
        raise ValueError("baseline and candidate calibration cell IDs differ")
    baseline_fits = fits(args.baseline_hists)
    candidate_fits = fits(args.candidate_hists)
    common = sorted(baseline_fits.keys() & candidate_fits.keys())
    paired_chi2 = [(cell, baseline_fits[cell]["chi2_ndf"], candidate_fits[cell]["chi2_ndf"])
                   for cell in common if baseline_fits[cell]["chi2_ndf"] is not None
                   and candidate_fits[cell]["chi2_ndf"] is not None]
    if not paired_chi2:
        raise ValueError("no high-gain fits with positive degrees of freedom in both files")
    changes = sorted(((old - new, cell) for cell, old, new in paired_chi2), reverse=True)
    selected = {}
    for cell in (896, 903):
        selected[str(cell)] = {
            "baseline_fit": baseline_fits.get(cell), "candidate_fit": candidate_fits.get(cell),
            "baseline_calibration": baseline_calib[cell], "candidate_calibration": candidate_calib[cell],
        }
    summary = {
        "note": "Numerical comparison only; no scientific acceptance is inferred.",
        "baseline_fit_count": len(baseline_fits), "candidate_fit_count": len(candidate_fits),
        "common_fit_count": len(common),
        "fits_lost": sorted(baseline_fits.keys() - candidate_fits.keys()),
        "fits_gained": sorted(candidate_fits.keys() - baseline_fits.keys()),
        "median_chi2_ndf_baseline": median(old for _, old, _ in paired_chi2),
        "median_chi2_ndf_candidate": median(new for _, _, new in paired_chi2),
        "chi2_ndf_improved_count": sum(new < old for _, old, new in paired_chi2),
        "chi2_ndf_worsened_count": sum(new > old for _, old, new in paired_chi2),
        "largest_chi2_ndf_improvements": [{"cell": cell, "delta": delta} for delta, cell in changes[:10]],
        "largest_chi2_ndf_regressions": [{"cell": cell, "delta": delta} for delta, cell in changes[-10:]],
        "selected_cells": selected,
    }
    args.out.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved comparison: {args.out}")
    print(f"Saved HG fits: baseline {len(baseline_fits)}, candidate {len(candidate_fits)}, common {len(common)}")
    print(f"Median chi2/ndf: {summary['median_chi2_ndf_baseline']:.2f} -> {summary['median_chi2_ndf_candidate']:.2f}")
    for cell in (896, 903):
        old, new = baseline_fits.get(cell), candidate_fits.get(cell)
        print(f"Cell {cell}: baseline={old} candidate={new}")
    print(summary["note"])


if __name__ == "__main__":
    main()
