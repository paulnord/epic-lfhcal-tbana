#!/usr/bin/env python3
"""Controlled synthetic same-histogram drawing comparison; not a beam replay.

Requires the unchanged AdaptiveLangau.h from upstream PR #89. Both models are
fit to each identical deterministic (Asimov) histogram with identical starts,
bounds, range and ROOT options. Truth is adaptive, so this is NOT an unbiased
benchmark of physical model choice. All cases/statuses are retained.
"""
import argparse
import json
from pathlib import Path
import ROOT

p = argparse.ArgumentParser(__doc__)
p.add_argument('--adaptive-header', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--source-dir', type=Path, default=Path(__file__).resolve().parents[1],
               help='NewStructure directory containing the plotting fix (PR #16)')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
ROOT.gROOT.SetBatch(True)
source_dir = a.source_dir.resolve()
if not (source_dir / 'FitCurveDrawing.h').is_file():
    p.error('requires plotting PR #16; use --source-dir PATH/TO/NewStructure')
ROOT.gInterpreter.AddIncludePath(str(source_dir))
assert ROOT.gInterpreter.Declare('#include "FitCurveDrawing.h"\n#include "' + str(a.adaptive_header.resolve()) + '"')
source = (source_dir / 'TileSpectra.cc').read_text()
start = source.index('double TileSpectra::langaufun(')
end = source.index('\n\ndouble TileSpectra::langauWithPedestal(', start)
assert ROOT.gInterpreter.Declare(source[start:end].replace('TileSpectra::langaufun', 'sample_legacy'))
assert ROOT.gInterpreter.Declare('''
double sample_adaptive(double* x, double* p) {
 return lfhcal::adaptive_langau::Convolution({p[0],p[1],p[2],p[3]},
   [](double u) { return TMath::Landau(u,0.,1.); })(x[0]);
}
''')
ROOT.Math.MinimizerOptions.SetDefaultMaxFunctionCalls(1000)
ROOT.Math.MinimizerOptions.SetDefaultMaxIterations(100)
import matplotlib.pyplot as plt
fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
results = []
# Predeclared narrow regime and well-resolved control. Do not select by outcome.
for row, (name, truth) in enumerate([
    ('Narrow Landau / broad Gaussian', [.121920, 22.555322, 13519.316, 7.889414]),
    ('Well-resolved control', [2., 22., 13519.316, 3.])]):
    h = ROOT.TH1D('hist'+str(row), '', 80, 0., 80.)
    generator = ROOT.TF1('truth'+str(row), ROOT.sample_adaptive, 3.5, 67.71, 4)
    generator.SetParameters(*truth)
    centers = [h.GetBinCenter(i) for i in range(1, 81)]
    counts = [generator.Eval(x) for x in centers]
    for i, y in enumerate(counts, 1):
        h.SetBinContent(i, y)
        h.SetBinError(i, y**.5)
    case = dict(name=name, truth=truth, bin_centers=centers, counts=counts, fits=[])
    for col, (label, evaluator, color) in enumerate([
        ('Legacy 100-step', ROOT.sample_legacy, '#a84300'),
        ('Adaptive', ROOT.sample_adaptive, '#126d9b')]):
        fit = ROOT.TF1('fit'+str(row)+str(col), evaluator, 3.5, 67.71, 4)
        fit.SetParameters(*truth)
        for i, (low, high) in enumerate([(.05, 10.), (10., 35.), (1000., 30000.), (.5, 15.)]):
            fit.SetParLimits(i, low, high)
        result = h.Fit(fit, 'QRLN0S')
        state = [fit.GetParameter(i) for i in range(4)]
        curve = ROOT.lfhcal.SampleMipFit(fit, 0., 80.)
        assert state == [fit.GetParameter(i) for i in range(4)]
        xs = [curve.GetPointX(i) for i in range(curve.GetN())]
        ys = [curve.GetPointY(i) for i in range(curve.GetN())]
        for i in range(curve.GetN()):
            assert ys[i] == fit.Eval(xs[i])
        ax = axes[row, col]
        ax.step(centers, counts, where='mid', color='.65', lw=1., label='Same synthetic histogram')
        ax.plot(xs, ys, color=color, lw=.7, label='Exact fitted evaluator (dense)')
        bx = [x for x in centers if 3.5 <= x <= 67.71]
        ax.plot(bx, [fit.Eval(x) for x in bx], 'o', ms=2.5, mfc='none', color=color, label='Fitted bin-center predictions')
        ax.axvspan(0., 3.5, color='.9'); ax.axvspan(67.71, 80., color='.9')
        ax.set(xlim=(0.,80.), xlabel='ADC', ylabel='Model counts / unit-width bin',
               title=f'{name}: {label}\nstatus {int(result)}, width={state[0]:.5g}, sigma={state[3]:.5g}')
        ax.legend(fontsize=7)
        case['fits'].append(dict(model=label, status=int(result), valid=bool(result.IsValid()),
            parameters=state, points=curve.GetN(), min_fcn=result.MinFcnValue(),
            fit_range=[fit.GetXmin(),fit.GetXmax()]))
    results.append(case)
fig.suptitle('Same histogram, same starts/bounds/options; each curve uses its own fitted callback', fontsize=12)
fig.supxlabel('Synthetic adaptive-generated bin-center expectations, no random noise; shaded regions are outside the fit window. Not beam data.', fontsize=9)
fig.savefig(a.output / 'same-histogram-fit-curves.png', dpi=160)
(a.output / 'same-histogram-fit-curves.json').write_text(json.dumps(dict(root=ROOT.gROOT.GetVersion(), options='QRLN0S (no I)', cases=results), indent=2)+'\n')
for case in results:
    print(case['name'], case['fits'], flush=True)
