#!/usr/bin/env python3
"""Compare ROOT Landau--Gaussian implementations on preserved E1 spectra.

This is a diagnostic only.  It does not modify calibration files or rerun the
production chain.  The primary case is cell 896, where the fixed-grid Langau
curve is visibly undersampled.
"""
from array import array
import json
from pathlib import Path
import sys
import time

import ROOT

ROOT.gROOT.SetBatch(True)
ROOT.gStyle.SetOptStat(0)
ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.FATAL)

BASE = Path(__file__).resolve().parents[4]
DEFAULT_INPUT = BASE / "local-results/fullset-e1-adaptive-review-20260921/imported/fullset-e1-repro/refine5"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "local-results/langau-tool-comparison"
CELLS = (896, 835, 898, 1223, 640)
SHIFT = 0.22278298


def declare_models():
    support = Path(__file__).resolve().parent / "fixed_width_numerics.h"
    ROOT.gInterpreter.Declare(f'''\
#include "{support}"
#include <TF1Convolution.h>
#include <TMath.h>
double compare_legacy(double *x, double *p) {{
  const double mpc = p[1] + {SHIFT} * p[0];
  const double low = x[0] - 5.0*p[3], high = x[0] + 5.0*p[3];
  const int np = 100;
  const double step = (high-low)/np;
  double sum = 0;
  for (int i=1; i<=np/2; ++i) {{
    double t=low+(i-.5)*step;
    sum += TMath::Landau(t,mpc,p[0])/p[0]*TMath::Gaus(x[0],t,p[3]);
    t=high-(i-.5)*step;
    sum += TMath::Landau(t,mpc,p[0])/p[0]*TMath::Gaus(x[0],t,p[3]);
  }}
  return p[2]*step*sum*0.3989422804014/p[3];
}}
double compare_adaptive(double *x, double *p) {{
  return fixed_width::Convolution({{p[0],p[1],p[2],p[3]}},
    [](double u) {{ return TMath::Landau(u,0.,1.); }}, 1e-10, 5.0)(x[0]);
}}
double compare_tf1conv(double *x, double *p) {{
  static TF1 landau("compare_landau", "landau", -200., 400.);
  static TF1 gauss("compare_gauss", "gaus", -200., 400.);
  static TF1Convolution conv(&landau, &gauss, -200., 400., true);
  conv.SetNofPointsFFT(4096);
  const double params[5] = {{1., p[1] + {SHIFT}*p[0], p[0], 0., p[3]}};
  conv.SetParameters(params);
  const double xx=x[0];
  return p[2]*conv(&xx, params);
}}
''')


def root_file(path):
    files = list(path.glob("*_Hists.root"))
    if len(files) != 1:
        raise RuntimeError(f"expected one histogram file in {path}, found {files}")
    result = ROOT.TFile.Open(str(files[0]), "READ")
    if not result or result.IsZombie():
        raise RuntimeError(f"cannot open {files[0]}")
    return result


def fit_tf1(h, title, callback, start, limits, low, high):
    model = ROOT.TF1(title, getattr(ROOT, callback), low, high, 4)
    model.SetParameters(array("d", start))
    model.SetParNames("Width", "MP", "Area", "GSigma")
    for i, (lo, hi) in enumerate(limits):
        model.SetParLimits(i, lo, hi)
    began = time.monotonic()
    result = h.Fit(model, "QRLMN0S")
    elapsed = time.monotonic() - began
    return model, result, elapsed


def roofit_curve(h, kind, start, limits, low, high):
    """Evaluate RooFit convolutions at fixed parameters from the saved fit.

    RooNumConvPdf is intentionally tested as a curve evaluator here.  During
    an unconstrained Minuit fit it can visit parameter combinations for which
    its infinite-range integrator fails; that behavior is itself recorded.
    """
    x = ROOT.RooRealVar(f"x_{kind}", "ADC", h.GetXaxis().GetXmin(), h.GetXaxis().GetXmax())
    x.setRange("fit", low, high)
    x.setBins(2048, "cache")
    width = ROOT.RooRealVar(f"width_{kind}", "Landau width", start[0])
    mp = ROOT.RooRealVar(f"mp_{kind}", "Landau MPV", start[1])
    sigma = ROOT.RooRealVar(f"sigma_{kind}", "Gaussian sigma", start[3])
    for parameter in (width, mp, sigma):
        parameter.setConstant(True)
    # RooLandau's mean parameter is already its most-probable value.  The
    # 0.22278298 correction belongs to ROOT's TMath::Landau convention used
    # by the legacy Langau helper and must not be applied a second time here.
    mean = mp
    zero = ROOT.RooConstVar(f"zero_{kind}", "Gaussian mean", 0.)
    landau = ROOT.RooLandau(f"landau_{kind}", "Landau", x, mean, width)
    gauss = ROOT.RooGaussian(f"gauss_{kind}", "Gaussian", x, zero, sigma)
    if kind.startswith("roofit_fft"):
        conv = ROOT.RooFFTConvPdf(f"conv_{kind}", "Landau x Gaussian", x, landau, gauss)
    else:
        conv = ROOT.RooNumConvPdf(f"conv_{kind}", "Landau x Gaussian", x, landau, gauss)
        conv.setConvolutionWindow(mean, sigma, 5.0)
    norm = ROOT.RooArgSet(x)
    xs = [low + (high-low)*i/400. for i in range(401)]
    ys = []
    for value in xs:
        x.setVal(value)
        ys.append(float(conv.getVal(norm)))
    peak_index = max(range(len(ys)), key=ys.__getitem__)
    half = ys[peak_index] / 2.
    left = next((xs[i] for i in range(peak_index, -1, -1) if ys[i] <= half), xs[0])
    right = next((xs[i] for i in range(peak_index, len(ys)) if ys[i] <= half), xs[-1])
    return {"parameters": start, "peak": xs[peak_index], "fwhm": right-left,
            "curve_max": ys[peak_index], "samples": len(xs), "mode": "fixed_saved_parameters",
            "_xs": xs, "_ys": ys}


def roofit_fft_fit(h, start, limits, low, high):
    """Fit an extended RooFFTConvPdf to the binned histogram."""
    x = ROOT.RooRealVar("fit_x", "ADC", h.GetXaxis().GetXmin(), h.GetXaxis().GetXmax())
    x.setRange("fit", low, high)
    x.setBins(4096, "cache")
    width = ROOT.RooRealVar("fit_width", "Landau width", start[0], max(1e-4, limits[0][0]), limits[0][1])
    mp = ROOT.RooRealVar("fit_mp", "Landau MPV", start[1], limits[1][0], limits[1][1])
    sigma = ROOT.RooRealVar("fit_sigma", "Gaussian sigma", start[3], max(1e-4, limits[3][0]), limits[3][1])
    yield_var = ROOT.RooRealVar("fit_yield", "signal yield", start[2], 1., max(1e7, 10.*h.GetEntries()))
    mean = ROOT.RooFormulaVar("fit_mean", "@0 + 0.22278298*@1", ROOT.RooArgList(mp, width))
    zero = ROOT.RooConstVar("fit_zero", "Gaussian mean", 0.)
    landau = ROOT.RooLandau("fit_landau", "Landau", x, mean, width)
    gauss = ROOT.RooGaussian("fit_gauss", "Gaussian", x, zero, sigma)
    conv = ROOT.RooFFTConvPdf("fit_conv", "Landau x Gaussian", x, landau, gauss)
    conv.setBufferFraction(.25)
    extended = ROOT.RooExtendPdf("fit_extended", "extended convolution", conv, yield_var)
    data = ROOT.RooDataHist("fit_data", "histogram", ROOT.RooArgList(x), h)
    began = time.monotonic()
    result = extended.fitTo(data, ROOT.RooFit.Save(True), ROOT.RooFit.Extended(True),
                             ROOT.RooFit.Range("fit"), ROOT.RooFit.PrintLevel(-1),
                             ROOT.RooFit.Strategy(1), ROOT.RooFit.Minimizer("Minuit2", "migrad"))
    return {"parameters": [width.getVal(), mp.getVal(), yield_var.getVal(), sigma.getVal()],
            "status": int(result.status()), "covariance": int(result.covQual()),
            "valid": bool(result.status() == 0), "min_nll": result.minNll(),
            "seconds": time.monotonic() - began}


def params_from_tf1(model):
    return [model.GetParameter(i) for i in range(4)]


def record_tf1(model, result, elapsed):
    return {"parameters": params_from_tf1(model), "status": int(result),
            "valid": bool(result.IsValid()), "chi2": model.GetChisquare(),
            "ndf": model.GetNDF(), "seconds": elapsed}


def record_roofit(result, objects, elapsed):
    width, mp, area, sigma, _, _ = objects
    return {"parameters": [width.getVal(), mp.getVal(), area.getVal(), sigma.getVal()],
            "status": int(result.status()), "covariance": int(result.covQual()),
            "valid": bool(result.status() == 0), "min_nll": result.minNll(),
            "seconds": elapsed}


def main():
    input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    OUT.mkdir(parents=True, exist_ok=True)
    declare_models()
    source = root_file(input_dir)
    rows = []
    for cell in CELLS:
        h = source.Get(f"IndividualCellsTrigg/hspectramipTriggADCCellID{cell}")
        saved = source.Get(f"IndividualCellsTrigg/fmipmipTriggHGCellID{cell}")
        if not h or not saved:
            continue
        h = h.Clone(f"comparison_cell_{cell}")
        h.SetDirectory(0)
        low, high = saved.GetXmin(), saved.GetXmax()
        start = [saved.GetParameter(i) for i in range(4)]
        limits = []
        for i in range(4):
            lo, hi = array("d", [0.]), array("d", [0.])
            saved.GetParLimits(i, lo, hi)
            limits.append((lo[0], hi[0]))
        cell_row = {"cell": cell, "entries": h.GetEntries(), "range": [low, high],
                    "saved_parameters": start, "tools": {}}
        plot_models = []
        plot_roofit = []
        for label, callback in (("legacy", "compare_legacy"),
                                ("adaptive", "compare_adaptive"),
                                ("tf1convolution_fft", "compare_tf1conv")):
            model, result, elapsed = fit_tf1(h, f"{label}_{cell}", callback, start, limits, low, high)
            cell_row["tools"][label] = record_tf1(model, result, elapsed)
            if cell in CELLS:
                plot_models.append((label, model.Clone(f"plot_{label}_{cell}")))
        for label in ("roofit_fft", "roofit_numeric"):
            began = time.monotonic()
            try:
                cell_row["tools"][label] = roofit_curve(h, label, start, limits, low, high)
                cell_row["tools"][label]["seconds"] = time.monotonic() - began
            except Exception as error:
                cell_row["tools"][label] = {"error": str(error), "seconds": time.monotonic() - began}
        try:
            cell_row["tools"]["roofit_fft_fit"] = roofit_fft_fit(h, start, limits, low, high)
            if cell in CELLS and "parameters" in cell_row["tools"]["roofit_fft_fit"]:
                fitted = cell_row["tools"]["roofit_fft_fit"]["parameters"]
                plot_roofit.append(("roofit_fft_fit", roofit_curve(h, "roofit_fft_fit", fitted, limits, low, high)))
        except Exception as error:
            cell_row["tools"]["roofit_fft_fit"] = {"error": str(error)}
        rows.append(cell_row)
        if cell in CELLS and plot_models:
            canvas = ROOT.TCanvas(f"langau_tool_comparison_{cell}", f"cell {cell}", 1200, 800)
            h.SetTitle(f"FullSetE_1 cell {cell}: convolution choices;ADC;counts")
            h.SetMinimum(0.0)
            h.SetMaximum(max(1.0, 1.25*h.GetMaximum()))
            h.GetXaxis().SetRangeUser(low, high)
            h.Draw("hist")
            colors = {"legacy": ROOT.kOrange + 7, "adaptive": ROOT.kAzure + 1,
                      "tf1convolution_fft": ROOT.kGreen + 2}
            legend = ROOT.TLegend(.58, .68, .88, .88)
            for label, model in plot_models:
                model.SetRange(low, high)
                model.SetLineColor(colors[label]); model.SetLineWidth(3)
                model.Draw("same")
                legend.AddEntry(model, label, "l")
            roofit_graphs = []
            for label, curve in plot_roofit:
                # RooFit returns a normalized PDF. Convert it to expected
                # counts per histogram bin using the fitted/saved yield.
                scale = curve["parameters"][2] * h.GetXaxis().GetBinWidth(1)
                graph = ROOT.TGraph(len(curve["_xs"]), array("d", curve["_xs"]),
                                    array("d", [y*scale for y in curve["_ys"]]))
                graph.SetName(f"plot_{label}_{cell}")
                if label == "roofit_fft_fit":
                    graph.SetLineColor(ROOT.kRed + 1); graph.SetLineStyle(1)
                elif label == "roofit_fft":
                    graph.SetLineColor(ROOT.kMagenta + 1); graph.SetLineStyle(2)
                else:
                    graph.SetLineColor(ROOT.kBlack); graph.SetLineStyle(3)
                graph.SetLineWidth(3)
                graph.Draw("L same")
                roofit_graphs.append(graph)
                legend.AddEntry(graph, label.replace("_", " ") + (" (fit)" if label == "roofit_fft_fit" else " (saved params)"), "l")
            legend.Draw(); canvas.SaveAs(str(OUT / f"cell{cell}-fit-comparison.png"))
            canvas.SaveAs(str(OUT / f"cell{cell}-fit-comparison.pdf"))
        print(json.dumps(cell_row, sort_keys=True))
    source.Close()
    (OUT / "results.json").write_text(json.dumps({"input": str(input_dir), "cells": rows}, indent=2) + "\n")


if __name__ == "__main__":
    main()
