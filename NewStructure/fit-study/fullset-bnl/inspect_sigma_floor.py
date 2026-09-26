#!/usr/bin/env python3
"""Inspect selected cells before and after the HGCROC Gaussian pedestal-sigma floor."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e1-bnl"))
from compare import fits  # noqa: E402

SETS = {
    "b1": "FullSetB_1", "b2": "FullSetB_2", "c2": "FullSetC_2",
    "d1": "FullSetD_1", "f1": "FullSetF_1", "f2": "FullSetF_2",
    "g1": "FullSetG_1", "g2": "FullSetG_2",
}
TARGETS = {
    "b1": [1024],
    "b2": [67, 131, 515, 518],
    "c2": [1479],
    "d1": [1095],
    "f1": [1024], "f2": [1024], "g1": [1024], "g2": [1024],
}


def calib(path):
    out = {}
    for line in path.read_text().splitlines():
        f = line.split()
        if len(f) == 18 and f[0].isdigit():
            out[int(f[0])] = {
                "ped": float(f[6]), "scale": float(f[9]), "bc": int(f[17])
            }
    return out


def paths(root, code, set_name, adaptive=False):
    d = root / (f"adaptive-fullset-{code}-repro/refine5" if adaptive else f"{code}/refine5")
    stem = f"rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{set_name}"
    return d / f"{stem}_calib.txt", d / f"{stem}_Hists.root"


def show(label, root, code, set_name, cell, adaptive=False):
    cp, hp = paths(root, code, set_name, adaptive)
    c = calib(cp)
    f = fits(hp)
    if cell not in f:
        return f"{label:12s} absent"
    x = f[cell]
    ped = c[cell]["ped"]
    return (
        f"{label:12s} wL={x['landau_width']:.6g} mpv={x['mpv']:.6g} "
        f"sigma={x['gaussian_sigma']:.6g} sig/ped={x['gaussian_sigma']/ped:.6g} "
        f"sig/wL={x['gaussian_sigma']/x['landau_width']:.6g} "
        f"chi2/ndf={x['chi2_ndf']:.6g}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adaptive-root", type=Path, required=True)
    ap.add_argument("--before-root", type=Path, required=True)
    ap.add_argument("--after-root", type=Path, required=True)
    args = ap.parse_args()

    for code, cells in TARGETS.items():
        set_name = SETS[code]
        for cell in cells:
            print(f"===== {code} cell {cell} =====")
            print(show("adaptive", args.adaptive_root, code, set_name, cell, True))
            print(show("before-floor", args.before_root, code, set_name, cell))
            print(show("sigma-floor", args.after_root, code, set_name, cell))
            print()


if __name__ == "__main__":
    main()
