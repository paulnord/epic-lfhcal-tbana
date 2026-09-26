#!/usr/bin/env python3
"""Plot published cross-FullSet MIP calibrations for stable control cells."""

import argparse
from pathlib import Path
import re

import ROOT

ROOT.gROOT.SetBatch(True)
ROOT.gStyle.SetOptStat(0)

CONTROL_CELLS = (130, 965, 1346, 1600, 2244, 2755)
ORDER = ("B1","B2","C1","C2","C3","D1","D2","E1","E2","E3","F1","F2","G1","G2")

CONFIG = {
    "B1": "43 V, RF9 CC10, (0,0)",
    "B2": "43 V, RF9 CC10, (-10,5)",
    "C1": "44 V, RF9 CC5, (-15,10)",
    "C2": "44 V, RF9 CC5, (10,-5)",
    "C3": "44 V, RF9 CC5, (0,0)",
    "D1": "45 V, RF9 CC4, (0,0)",
    "D2": "45 V, RF9 CC4, (0,0)",
    "E1": "44 V, RF12 CC3, (0,0)",
    "E2": "44 V, RF12 CC3, (0,0)",
    "E3": "44 V, RF12 CC3, (10,-10)",
    "F1": "45 V, RF12 CC3, (-10,-5)",
    "F2": "45 V, RF12 CC3, (10,-10)",
    "G1": "45 V, RF12 CC3, (-10,-10)",
    "G2": "45 V, RF12 CC3, (0,0)",
}

FAMILY_COLORS = {
    "B": ROOT.kRed + 1,
    "C": ROOT.kBlue + 1,
    "D": ROOT.kMagenta + 1,
    "E": ROOT.kCyan + 2,
    "F": ROOT.kGreen + 2,
    "G": ROOT.kViolet + 1,
}


def read_calib(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        f = line.split()
        if len(f) == 18 and f[0].isdigit():
            out[int(f[0])] = {
                "layer": int(f[1]),
                "row": int(f[2]),
                "col": int(f[3]),
                "module": int(f[4]),
                "scale": float(f[9]),
                "width": float(f[10]),
                "bc": int(f[17]),
            }
    return out


def set_key(path):
    m = re.search(r"FullSet([A-G])_([0-9]+)", path.name)
    return f"{m.group(1)}{m.group(2)}" if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    sets = {}
    for path in args.reference_dir.glob("calib_SPS-H2_FullSet*.txt"):
        key = set_key(path)
        if key in ORDER:
            sets[key] = read_calib(path)

    missing = [key for key in ORDER if key not in sets]
    if missing:
        raise SystemExit(f"missing published calibrations: {missing}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    c = ROOT.TCanvas("c_controls", "Stable control cells", 1350, 900)
    c.SetBottomMargin(0.20)
    c.SetTopMargin(0.12)
    c.Print(str(args.out) + "[")

    for cell in CONTROL_CELLS:
        rows = [(key, sets[key][cell]) for key in ORDER]
        geo = rows[0][1]

        scales = [row["scale"] for _, row in rows if row["scale"] > -999]
        ymin = min(scales) * 0.88
        ymax = max(scales) * 1.12

        frame = ROOT.TH1D(
            f"frame_{cell}",
            (
                f"Stable control cell {cell} "
                f"(module {geo['module']}, layer {geo['layer']}, row {geo['row']}, col {geo['col']});"
                "FullSet;published ScaleH (ADC)"
            ),
            len(ORDER), 0.5, len(ORDER) + 0.5,
        )
        frame.SetMinimum(ymin)
        frame.SetMaximum(ymax)
        for i, key in enumerate(ORDER, start=1):
            frame.GetXaxis().SetBinLabel(i, key)
        frame.GetXaxis().LabelsOption("v")
        frame.Draw("axis")

        keep = [frame]
        for i, (key, row) in enumerate(rows, start=1):
            family = key[0]
            marker = ROOT.TMarker(i, row["scale"], 20)
            marker.SetMarkerColor(FAMILY_COLORS[family])
            marker.SetMarkerSize(1.25)
            marker.Draw()
            keep.append(marker)

        # Join points only within the same FullSet family.
        for family in ("B","C","D","E","F","G"):
            pts = [(i, rows[i-1][1]["scale"]) for i,key in enumerate(ORDER, start=1) if key[0] == family]
            if len(pts) > 1:
                g = ROOT.TGraph(len(pts))
                for j,(x,y) in enumerate(pts):
                    g.SetPoint(j,x,y)
                g.SetLineColor(FAMILY_COLORS[family])
                g.SetLineWidth(2)
                g.Draw("L")
                keep.append(g)

        latex = ROOT.TLatex()
        latex.SetNDC(True)
        latex.SetTextSize(0.025)
        latex.DrawLatex(
            0.10, 0.94,
            "Run config: bias V / RF / CC / table (x,y); colors group repeated FullSet families"
        )
        config_text = "   ".join(
            [
                "B:43V RF9 CC10",
                "C:44V RF9 CC5",
                "D:45V RF9 CC4",
                "E:44V RF12 CC3",
                "F/G:45V RF12 CC3",
            ]
        )
        latex.DrawLatex(0.10, 0.90, config_text)
        keep.append(latex)

        c.Print(str(args.out))

    c.Print(str(args.out) + "]")
    print(f"Saved {len(CONTROL_CELLS)} stable-control pages: {args.out}")


if __name__ == "__main__":
    main()
