#!/usr/bin/env python3
"""Plot every fit changed by a full-set replay, overlaying available fit methods."""

import argparse
import json
from pathlib import Path
import sys

import ROOT

ROOT.gROOT.SetBatch(True)
ROOT.gStyle.SetOptStat(0)

SET_NAMES = {
    "b1": "FullSetB_1", "b2": "FullSetB_2", "c2": "FullSetC_2",
    "c3": "FullSetC_3", "d1": "FullSetD_1", "e1": "FullSetE_1",
    "e2": "FullSetE_2", "e3": "FullSetE_3", "f1": "FullSetF_1",
    "f2": "FullSetF_2", "g1": "FullSetG_1", "g2": "FullSetG_2",
}

METHODS = (
    ("adaptive", ROOT.kBlue + 1, 1),
    ("pre-floor", ROOT.kRed + 1, 2),
    ("floor-1.0", ROOT.kMagenta + 1, 3),
    ("floor-0.1", ROOT.kGreen + 2, 1),
)

FAMILY_COLORS = {
    "B": ROOT.kRed + 1,
    "C": ROOT.kBlue + 1,
    "D": ROOT.kMagenta + 1,
    "E": ROOT.kCyan + 2,
    "F": ROOT.kGreen + 2,
    "G": ROOT.kViolet + 1,
}


def calib(path: Path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        f = line.split()
        if len(f) == 18 and f[0].isdigit():
            out[int(f[0])] = {
                "pedestal_sigma_h": float(f[6]),
                "mip_scale_h": float(f[9]),
                "mip_width_h": float(f[10]),
                "bad_channel": int(f[17]),
            }
    return out


def published_family_values(reference_dir: Path, cell: int):
    values = []
    for path in sorted(reference_dir.glob("calib_SPS-H2_FullSet*.txt")):
        stem = path.stem.replace("calib_SPS-H2_FullSet", "")
        if "_" not in stem:
            continue
        family = stem.split("_", 1)[0]
        run_tag = f"FullSet{stem}"
        row = calib(path).get(cell)
        if not row:
            continue
        scale = row["mip_scale_h"]
        width = row["mip_width_h"]
        if scale <= -999 or width <= -999:
            continue
        values.append({
            "family": family,
            "run": run_tag,
            "scale": scale,
            "width": width,
        })
    return values


def files(root: Path, code: str, set_name: str, adaptive=False):
    d = root / (f"adaptive-fullset-{code}-repro/refine5" if adaptive else f"{code}/refine5")
    stem = f"rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{set_name}"
    return d / f"{stem}_calib.txt", d / f"{stem}_Hists.root"


def load_cell(root: Path, code: str, set_name: str, cell: int, adaptive=False):
    cp, hp = files(root, code, set_name, adaptive)
    if not cp.is_file() or not hp.is_file():
        return None

    cals = calib(cp)
    if cell not in cals:
        return None

    rf = ROOT.TFile.Open(str(hp))
    if not rf or rf.IsZombie():
        return None

    directory = rf.Get("IndividualCellsTrigg")
    if not directory:
        rf.Close()
        return None

    hname = f"hspectramipTriggADCCellID{cell}"
    fname = f"fmipmipTriggHGCellID{cell}"
    hist = directory.Get(hname)
    fit = directory.Get(fname)

    hist_clone = hist.Clone(f"{hname}_{code}_{root.name}") if hist else None
    fit_clone = fit.Clone(f"{fname}_{code}_{root.name}") if fit else None
    if hist_clone:
        hist_clone.SetDirectory(0)

    rf.Close()

    return {
        "hist": hist_clone,
        "fit": fit_clone,
        "calib": cals[cell],
    }


def fmtfit(label, data):
    if not data or not data["fit"]:
        return f"{label}: no saved fit"
    f = data["fit"]
    ped = data["calib"]["pedestal_sigma_h"]
    w = f.GetParameter(0)
    mpv = f.GetParameter(1)
    sig = f.GetParameter(3)
    ndf = f.GetNDF()
    chi = f.GetChisquare() / ndf if ndf > 0 else float("nan")
    return (
        f"{label}: wL={w:.3g}, MPV={mpv:.3g}, "
        f"#sigma={sig:.3g}, #sigma/ped={sig/ped:.3g}, #chi^{{2}}/ndf={chi:.3g}"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adaptive-root", type=Path, required=True)
    ap.add_argument("--pre-floor-root", type=Path, required=True)
    ap.add_argument("--candidate-root", type=Path, required=True)
    ap.add_argument("--floor1-root", type=Path)
    ap.add_argument(
        "--reference-dir",
        type=Path,
        help=(
            "Directory containing Fredi's published calib_SPS-H2_FullSet*.txt "
            "files. Defaults to <repo>/calibrations/TB2026."
        ),
    )
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if args.reference_dir is None:
        args.reference_dir = Path(__file__).resolve().parents[3] / "calibrations" / "TB2026"

    summary = json.loads((args.candidate_root / "summary.json").read_text(encoding="utf-8"))
    targets = []
    for kind in ("fits_lost", "fits_gained"):
        for code, cells in summary["totals"].get(kind, {}).items():
            for cell in cells:
                targets.append((code, int(cell), kind))
    targets.sort()

    roots = {
        "adaptive": (args.adaptive_root, True),
        "pre-floor": (args.pre_floor_root, False),
        "floor-0.1": (args.candidate_root, False),
    }
    if args.floor1_root:
        roots["floor-1.0"] = (args.floor1_root, False)

    args.out.parent.mkdir(parents=True, exist_ok=True)

    canvas = ROOT.TCanvas("c_changed", "Changed Langau fits", 1200, 900)
    canvas.Print(str(args.out) + "[")

    for code, cell, kind in targets:
        set_name = SET_NAMES[code]
        data = {
            label: load_cell(root, code, set_name, cell, adaptive)
            for label, (root, adaptive) in roots.items()
        }

        reference_path = args.reference_dir / f"calib_SPS-H2_{set_name}.txt"
        published = None
        if reference_path.is_file():
            published = calib(reference_path).get(cell)
        family_values = published_family_values(args.reference_dir, cell)

        base = None
        for label in ("adaptive", "pre-floor", "floor-0.1", "floor-1.0"):
            if label in data and data[label] and data[label]["hist"]:
                base = data[label]["hist"]
                break
        if not base:
            print(f"WARNING no histogram for {code} cell {cell}", file=sys.stderr)
            continue

        canvas.Clear()
        canvas.SetLogy(False)
        base.SetTitle(
            f"{code.upper()} cell {cell} ({kind.replace('_', ' ')});ADC;counts"
        )
        base.SetLineColor(ROOT.kBlack)
        base.SetMarkerStyle(20)
        base.SetMarkerSize(0.6)

        xmin = None
        xmax = None
        ymax = 0.0
        for label, _, _ in METHODS:
            d = data.get(label)
            if not d or not d["fit"]:
                continue
            f = d["fit"]
            xmin = f.GetXmin() if xmin is None else min(xmin, f.GetXmin())
            xmax = f.GetXmax() if xmax is None else max(xmax, f.GetXmax())

        if xmin is not None and xmax is not None and xmax > xmin:
            margin = 0.08 * (xmax - xmin)
            base.GetXaxis().SetRangeUser(xmin - margin, xmax + margin)

        for b in range(1, base.GetNbinsX() + 1):
            x = base.GetBinCenter(b)
            if xmin is not None and xmax is not None and not (xmin <= x <= xmax):
                continue
            ymax = max(ymax, base.GetBinContent(b))
        if ymax > 0:
            base.SetMaximum(ymax * 1.35)

        base.Draw("E")

        # Fredi's published ScaleH for this same cell in the other runs of
        # the same FullSet family.  Cross-family values are intentionally
        # omitted because those configurations have different operating settings.
        cross_run_hashes = []
        current_family = set_name.replace("FullSet", "").split("_", 1)[0]
        hash_height = base.GetMaximum() * 0.055
        for item in family_values:
            if item["run"] == set_name or item["family"] != current_family:
                continue
            hline = ROOT.TLine(item["scale"], 0.0, item["scale"], hash_height)
            hline.SetLineColor(FAMILY_COLORS.get(item["family"], ROOT.kGray + 2))
            hline.SetLineWidth(3)
            hline.Draw("same")
            cross_run_hashes.append(hline)

        legend = ROOT.TLegend(0.40, 0.52, 0.95, 0.90)
        legend.SetBorderSize(0)
        legend.SetFillStyle(0)
        legend.SetTextSize(0.025)
        legend.AddEntry(base, "data", "lep")

        keepalive = [base, legend]
        keepalive.extend(cross_run_hashes)
        for label, color, style in METHODS:
            if label not in data:
                continue
            d = data[label]
            if d and d["fit"]:
                f = d["fit"]
                f.SetLineColor(color)
                f.SetLineStyle(style)
                f.SetLineWidth(3)
                f.Draw("same")
                keepalive.append(f)
                legend.AddEntry(f, fmtfit(label, d), "l")
            else:
                legend.AddEntry(0, f"{label}: no saved fit", "")

        same_family_values = [
            item for item in family_values
            if item["family"] == set_name.replace("FullSet", "").split("_", 1)[0]
            and item["run"] != set_name
        ]
        if same_family_values:
            legend.AddEntry(
                0,
                "other Fredi runs in same family: short ticks near axis",
                "",
            )

        if published:
            pscale = published["mip_scale_h"]
            pwidth = published["mip_width_h"]
            pbc = published["bad_channel"]
            if pscale > -999 and pwidth > -999:
                refline = ROOT.TLine(pscale, 0.0, pscale, base.GetMaximum())
                refline.SetLineColor(ROOT.kOrange + 7)
                refline.SetLineStyle(7)
                refline.SetLineWidth(3)
                refline.Draw("same")
                keepalive.append(refline)
                legend.AddEntry(
                    refline,
                    f"Fredi published: ScaleH={pscale:.3g}, FWHM={pwidth:.3g}, BC={pbc}",
                    "l",
                )
            else:
                legend.AddEntry(
                    0,
                    f"Fredi published: no MIP calib (ScaleH={pscale:.0f}, FWHM={pwidth:.0f}, BC={pbc})",
                    "",
                )
        else:
            legend.AddEntry(0, "Fredi published calibration: unavailable", "")

        legend.Draw()

        note = ROOT.TLatex()
        note.SetNDC(True)
        note.SetTextSize(0.028)
        note.DrawLatex(
            0.12, 0.94,
            "Orange = current Fredi ScaleH; short ticks = same cell in same-family runs"
        )
        keepalive.append(note)

        canvas.Print(str(args.out))

    canvas.Print(str(args.out) + "]")
    print(f"Saved {len(targets)}-cell pathology PDF: {args.out}")


if __name__ == "__main__":
    main()
