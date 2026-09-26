#!/usr/bin/env python3
"""Compare changed full-set cells with the published TB2026 calibration files."""

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

REF_FILES = {
    code: f"calib_SPS-H2_{name}.txt"
    for code, name in SET_NAMES.items()
}

def read_calib(path):
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        f = line.split()
        if len(f) == 18 and f[0].isdigit():
            rows[int(f[0])] = {
                "pedestal_sigma_h": float(f[6]),
                "scale_h": float(f[9]),
                "width_h": float(f[10]),
                "bad_channel": int(f[17]),
            }
    return rows

def candidate_paths(root, code, set_name):
    d = root / code / "refine5"
    stem = f"rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{set_name}"
    return d / f"{stem}_calib.txt", d / f"{stem}_Hists.root"

def pct(new, old):
    if old in (0, -1000) or new == -1000:
        return None
    return 100.0 * (new - old) / old

def fmt(x):
    if x is None:
        return "-"
    return f"{x:.4g}"

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--candidate-root", type=Path, required=True)
    args = ap.parse_args()

    summary = json.loads((args.candidate_root / "summary.json").read_text(encoding="utf-8"))
    targets = {}
    for kind in ("fits_lost", "fits_gained"):
        for code, cells in summary["totals"].get(kind, {}).items():
            for cell in cells:
                targets[(code, int(cell))] = kind

    print("set cell kind         FrediScale FrediWidth BC  fit?  candScale candWidth  dScale% dWidth%")
    for (code, cell), kind in sorted(targets.items()):
        set_name = SET_NAMES[code]
        ref_path = args.repo / "calibrations" / "TB2026" / REF_FILES[code]
        cand_calib_path, cand_hist_path = candidate_paths(args.candidate_root, code, set_name)

        ref = read_calib(ref_path)[cell]
        cand = read_calib(cand_calib_path)[cell]
        saved = cell in fits(cand_hist_path)

        print(
            f"{code:3s} {cell:4d} {kind.replace('fits_',''):11s} "
            f"{ref['scale_h']:10.4f} {ref['width_h']:10.4f} {ref['bad_channel']:2d}  "
            f"{'yes' if saved else 'no ':3s} "
            f"{cand['scale_h']:10.4f} {cand['width_h']:10.4f} "
            f"{fmt(pct(cand['scale_h'], ref['scale_h'])):>8s} "
            f"{fmt(pct(cand['width_h'], ref['width_h'])):>8s}"
        )

    print()
    print("Note: if fit? is 'no', the candidate calibration value can be inherited/propagated")
    print("from the incoming refine4 calibration rather than produced by a new refine5 fit.")

if __name__ == "__main__":
    main()
