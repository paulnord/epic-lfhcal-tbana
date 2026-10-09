#!/usr/bin/env python3
"""PyROOT regression for the production MIP renderer; optional --figure FILE.png.

Runs directly against the evaluator extracted from TileSpectra.cc. It does not
refit or reconstruct experimental histogram counts. The cell-896 vector below
is rounded to the precision printed in the previous diagnostic plot.
"""
import argparse
from pathlib import Path
import ROOT


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--figure", type=Path)
    args = parser.parse_args()
    source_dir = Path(__file__).resolve().parents[1]
    ROOT.gROOT.SetBatch(True)
    ROOT.gInterpreter.AddIncludePath(str(source_dir))
    assert ROOT.gInterpreter.Declare('#include "FitCurveDrawing.h"\n#include "AdaptiveLangau.h"')
    source = (source_dir / "TileSpectra.cc").read_text()
    start = source.index("double TileSpectra::langaufun(")
    end = source.index("\n\nint TileSpectra::langaupro(", start)
    assert ROOT.gInterpreter.Declare(source[start:end].replace(
        "TileSpectra::langaufun", "drawing_test_legacy"))
    assert ROOT.gInterpreter.Declare('''
double drawing_test_adaptive(double* x, double* p) {
  return lfhcal::adaptive_langau::Convolution({p[0],p[1],p[2],p[3]},
    [](double u) { return TMath::Landau(u,0.,1.); })(x[0]);
}
''')
    fit = ROOT.TF1("cell896_legacy", ROOT.drawing_test_legacy, 3.5, 67.71, 4)
    fit.SetParameters(.121920, 22.555322, 13519.316, 7.889414)
    fit.SetNpx(1000)
    fit.SetLineColor(ROOT.kBlue)
    fit.SetLineWidth(7)
    fit.SetChisquare(13584.437)
    fit.SetNDF(61)
    def state():
        return (fit.GetXmin(), fit.GetXmax(), fit.GetNpx(), fit.GetLineWidth(),
                fit.GetLineColor(), fit.GetChisquare(), fit.GetNDF(),
                tuple(fit.GetParameter(i) for i in range(4)))
    before = state()
    curve = ROOT.lfhcal.SampleMipFit(fit, 0., 80.)
    assert curve.GetN() > 8000
    assert curve.GetPointX(0) == fit.GetXmin()
    assert abs(curve.GetPointX(curve.GetN()-1)-fit.GetXmax()) < 1e-12
    peak = max(curve.GetY())
    interpolation_error = 0.
    for i in range(curve.GetN()-1):
        x = (curve.GetPointX(i)+curve.GetPointX(i+1))/2
        linear = (curve.GetPointY(i)+curve.GetPointY(i+1))/2
        interpolation_error = max(interpolation_error, abs(linear-fit.Eval(x))/peak)
    assert interpolation_error < .005, interpolation_error
    canvas = ROOT.TCanvas("fit_drawing_test", "", 1000, 700)
    data = ROOT.TH1D("binning_only", "", 80, 0, 80)
    data.SetMaximum(1.1*peak)
    data.Draw()
    ROOT.lfhcal.DrawMipFit(fit, data, 0., 80., ROOT.kRed)
    canvas.Update()
    bins = canvas.GetListOfPrimitives().FindObject("cell896_legacy_bin_predictions")
    assert bins and bins.GetN() == 65
    for i in range(bins.GetN()):
        assert bins.GetPointY(i) == fit.Eval(bins.GetPointX(i))
    assert state() == before, "drawing mutated the fitted model"
    # ROOT's old production drawing path, with exactly its original Npx/range.
    old = ROOT.TF1(fit)
    old.SetName("old_drawing")
    old.SetRange(0., 2000.)
    old.Draw("same")
    canvas.Update()
    histogram = old.GetHistogram()
    assert histogram.GetNbinsX() == 1000
    old_curve = ROOT.TGraph(histogram)
    old_error = max(abs(old_curve.Eval(curve.GetPointX(i))-curve.GetPointY(i))
                    for i in range(curve.GetN()))/peak
    assert old_error > .1, old_error
    # A callback from a different integration method must stay that method.
    adaptive = ROOT.TF1("adaptive", ROOT.drawing_test_adaptive, 3.5, 67.71, 4)
    adaptive.SetParameters(1.327728,13.663332,13761.589,2.502781)
    adaptive_curve = ROOT.lfhcal.SampleMipFit(adaptive, 0., 80.)
    for i in range(0,adaptive_curve.GetN(),100):
        assert adaptive_curve.GetPointY(i) == adaptive.Eval(adaptive_curve.GetPointX(i))
    # An extreme parameter set must not silently degrade into coarse sampling.
    extreme = ROOT.TF1(fit)
    extreme.SetParameter(0,1.e-9)
    try:
        ROOT.lfhcal.SampleMipFit(extreme,0.,80.)
    except Exception:
        pass
    else:
        raise AssertionError("extreme fit must report unresolved sampling")
    # Rejected overlays must appear without replacing accepted-fit accessors.
    assert ROOT.gInterpreter.Declare('''
struct DrawingTestSpectrum {
  TF1* attempt;
  TH1* histogram;
  bool accepted;
  TF1* GetSignalModel(int) { return accepted ? attempt : nullptr; }
  TF1* GetSignalFitAttempt(int) { return attempt; }
  TH1* GetHG() { return histogram; }
  TH1* GetLG() { return histogram; }
};
bool check_rejected_overlay(TF1* fit, TH1* data) {
  DrawingTestSpectrum inclusive{fit,data,true}, triggered{fit,data,false};
  lfhcal::DrawRejectedMipFits(inclusive,triggered,1,0.,80.);
  bool label=false;
  for (auto* object : *gPad->GetListOfPrimitives())
    if (std::string(object->GetTitle()) == "Rejected triggered fit") label=true;
  return label && inclusive.GetSignalModel(1)==fit && !triggered.GetSignalModel(1);
}
''')
    canvas.Clear()
    data.Draw()
    assert ROOT.check_rejected_overlay(fit,data)
    canvas.Update()
    print(f"ROOT {ROOT.gROOT.GetVersion()}: {curve.GetN()} points; "
          f"max interpolation error/peak: old={old_error:.3%}, new={interpolation_error:.3%}")
    print("PASS: live legacy/adaptive evaluators, bin predictions, fit metadata, "
          "rejected overlay, sampling guard")
    if args.figure:
        import matplotlib.pyplot as plt
        xs = [curve.GetPointX(i) for i in range(curve.GetN())]
        ys = [curve.GetPointY(i) for i in range(curve.GetN())]
        fig, axes = plt.subplots(1,2,figsize=(12,4.8),layout="constrained")
        for ax in axes:
            ax.plot(xs,ys,color="#ba4b00",lw=.9,label="Actual optimized legacy function")
            ax.plot(xs,[old_curve.Eval(x) for x in xs],color="#006cba",lw=1.6,
                    label="Old drawing: 1,000 points / 2,000 ADC")
            ax.set_xlabel("ADC")
            ax.set_ylabel("Model counts / bin")
            ax.grid(alpha=.15)
        axes[0].set_xlim(3.5,60)
        axes[0].set_title("Same fitted parameters; different drawing")
        axes[0].legend(fontsize=8)
        axes[1].set_xlim(19,27)
        axes[1].set_title("Peak detail exposes missed oscillations")
        fig.suptitle("Cell 896 legacy fit — plotting audit",fontsize=15)
        fig.supxlabel("Reevaluated from published rounded parameters; no refit or experimental data reconstruction.",fontsize=9)
        args.figure.parent.mkdir(parents=True,exist_ok=True)
        fig.savefig(args.figure,dpi=160)


if __name__ == "__main__":
    main()
