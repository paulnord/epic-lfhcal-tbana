#!/usr/bin/env python3
"""Verify the late-stage inputs required by the full-production replay."""

from pathlib import Path
import sys


SETS = (
    ("b1", "B", "1"), ("b2", "B", "2"), ("c2", "C", "2"),
    ("c3", "C", "3"), ("d1", "D", "1"), ("e1", "E", "1"),
    ("e2", "E", "2"), ("e3", "E", "3"), ("f1", "F", "1"),
    ("f2", "F", "2"), ("g1", "G", "1"), ("g2", "G", "2"),
)


def main() -> int:
    root = Path(sys.argv[1])
    missing = []
    for code, letter, number in SETS:
        name = f"FullSet{letter}_{number}"
        source = root / f"adaptive-fullset-{code}-repro"
        stem = f"rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{name}"
        required = (
            source / "selected" / f"rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_{name}.root",
            source / "refine4" / f"rawHGCROC_wPedwMuon_wBC_Imp4R_Muon_{name}_calib.txt",
            source / "refine5" / f"{stem}_calib.txt",
            source / "refine5" / f"{stem}_Hists.root",
        )
        absent = [path for path in required if not path.is_file()]
        if absent:
            print(f"MISSING {code}")
            for path in absent:
                print(f"  {path}")
            missing.extend(absent)
        else:
            print(f"READY {code}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
