#!/usr/bin/env python3
"""Compare the cells changed by a sigma-floor replay with adaptive and an earlier replay."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e1-bnl"))
from compare import fits  # noqa: E402

SET_NAMES = {
    "b1": "FullSetB_1", "b2": "FullSetB_2", "c2": "FullSetC_2",
    "c3": "FullSetC_3", "d1": "FullSetD_1", "e1": "FullSetE_1",
    "e2": "FullSetE_2", "e3": "FullSetE_3", "f1": "FullSetF_1",
    "f2": "FullSetF_2", "g1": "FullSetG_1", "g2": "FullSetG_2",
}

def calib(path):
    out = {}
    for line in path.read_text().splitlines():
        f = line.split()
        if len(f) == 18 and f[0].isdigit():
            out[int(f[0])] = {"ped": float(f[6]), "scale": float(f[9]), "bc": int(f[17])}
    return out

def pair(root, code, set_name, adaptive=False):
    d = root / (f"adaptive-fullset-{code}-repro/refine5" if adaptive else f"{code}/refine5")
    stem = f"rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{set_name}"
    return d / f"{stem}_calib.txt", d / f"{stem}_Hists.root"

def describe(label, root, code, set_name, cell, adaptive=False):
    cp, hp = pair(root, code, set_name, adaptive)
    c = calib(cp)
    fs = fits(hp)
    if cell not in fs:
        return f"{label:14s} absent"
    x = fs[cell]
    ped = c[cell]["ped"]
    return (
        f"{label:14s} wL={x['landau_width']:.6g} mpv={x['mpv']:.6g} "
        f"sigma={x['gaussian_sigma']:.6g} sig/ped={x['gaussian_sigma']/ped:.6g} "
        f"sig/wL={x['gaussian_sigma']/x['landau_width']:.6g} "
        f"chi2/ndf={x['chi2_ndf']:.6g}"
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adaptive-root", type=Path, required=True)
    ap.add_argument("--before-root", type=Path, required=True,
                    help="Pre-floor fixed-grid rescue replay.")
    ap.add_argument("--candidate-root", type=Path, required=True)
    args = ap.parse_args()

    summary = json.loads((args.candidate_root / "summary.json").read_text())
    targets = {}
    for kind in ("fits_lost", "fits_gained"):
        for code, cells in summary["totals"].get(kind, {}).items():
            for cell in cells:
                targets[(code, cell)] = kind

    for (code, cell), kind in sorted(targets.items()):
        set_name = SET_NAMES[code]
        print(f"===== {code} cell {cell} ({kind}) =====")
        print(describe("adaptive", args.adaptive_root, code, set_name, cell, True))
        print(describe("pre-floor", args.before_root, code, set_name, cell))
        print(describe("sigma-floor-0.1", args.candidate_root, code, set_name, cell))
        print()

if __name__ == "__main__":
    main()
