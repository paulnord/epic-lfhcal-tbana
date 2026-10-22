#!/usr/bin/env python3
"""Old display versus faithful drawing at frozen parameters. No fitting occurs.

Input JSON is the preserved compare_fit_curve_samples.py output. Cell896 uses
published rounded parameters without experimental histogram reconstruction.
"""
import argparse
import json
from pathlib import Path
import ROOT

p = argparse.ArgumentParser(__doc__)
p.add_argument('--adaptive-header', type=Path, required=True)
p.add_argument('--frozen-fits', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
ROOT.gROOT.SetBatch(True)
b = Path(__file__).resolve().parents[1]
ROOT.gInterpreter.AddIncludePath(str(b))
assert ROOT.gInterpreter.Declare('#include "FitCurveDrawing.h"\n#include "' + str(a.adaptive_header.resolve()) + '"')
s = (b / 'TileSpectra.cc').read_text()
start = s.index('double TileSpectra::langaufun(')
end = s.index('\n\ndouble TileSpectra::langauWithPedestal(', start)
assert ROOT.gInterpreter.Declare(s[start:end].replace('TileSpectra::langaufun', 'audit_legacy'))
assert ROOT.gInterpreter.Declare('''
double audit_adaptive(double* x, double* p) {
 return lfhcal::adaptive_langau::Convolution({p[0],p[1],p[2],p[3]},
   [](double u) { return TMath::Landau(u,0.,1.); })(x[0]);
}
''')
frozen = json.loads(a.frozen_fits.read_text())['cases']
cases = [
    ('A. Historical cell 896: narrow legacy', ROOT.audit_legacy,
     [.121920,22.555322,13519.316,7.889414], None,
     'Rounded historical fit parameters; no recovered histogram'),
    ('B. Synthetic narrow case: frozen legacy fit', ROOT.audit_legacy,
     frozen[0]['fits'][0]['parameters'], frozen[0],
     'Synthetic histogram; saved fit status 0; no refit here'),
    ('C. Well-resolved control: frozen legacy fit', ROOT.audit_legacy,
     frozen[1]['fits'][0]['parameters'], frozen[1],
     'Synthetic control; saved fit status 0; no refit here'),
    ('D. Well-resolved control: frozen adaptive fit', ROOT.audit_adaptive,
     frozen[1]['fits'][1]['parameters'], frozen[1],
     'Same control histogram as C; different fitted evaluator')]
import matplotlib.pyplot as plt
fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout='constrained')
canvas = ROOT.TCanvas('audit_canvas','',800,600)
metadata = []
for i, (title, callback, parameters, data, provenance) in enumerate(cases):
    fit = ROOT.TF1('audit_fit'+str(i), callback, 3.5, 67.71, 4)
    fit.SetParameters(*parameters)
    fit.SetNpx(1000)
    curve = ROOT.lfhcal.SampleMipFit(fit, 0., 80.)
    xs = [curve.GetPointX(j) for j in range(curve.GetN())]
    ys = [curve.GetPointY(j) for j in range(curve.GetN())]
    old = ROOT.TF1(fit)
    old.SetName('audit_old'+str(i))
    old.SetRange(0., 2000.)
    canvas.Clear(); old.Draw(); canvas.Update()
    coarse = ROOT.TGraph(old.GetHistogram())
    old_y = [coarse.Eval(x) for x in xs]
    error = max(abs(y-z) for y,z in zip(ys,old_y))/max(ys)
    assert [fit.GetParameter(j) for j in range(4)] == parameters
    ax = axes.flat[i]
    if data:
        ax.step(data['bin_centers'], data['counts'], where='mid', color='.7', lw=.8, label='Frozen synthetic histogram')
        bx = [x for x in data['bin_centers'] if 3.5 <= x <= 67.71]
        ax.plot(bx, [fit.Eval(x) for x in bx], 'o', color='#ab4200', ms=2.5, mfc='none', label='Actual bin-center predictions')
    ax.plot(xs, old_y, color='#176db1', lw=1.5, label='Old display: 1000 samples / 2000 ADC')
    ax.plot(xs, ys, color='#ab4200', lw=.7, label='Faithful: identical callback + parameters')
    ax.axvspan(0.,3.5,color='.92'); ax.axvspan(67.71,80.,color='.92')
    ax.set(xlim=(0.,80.), xlabel='ADC', ylabel='Model value', title=title+'\n'+provenance)
    ax.legend(fontsize=7)
    ax.text(.98,.48, f'Max old-display discrepancy\n{error:.2%} of peak', ha='right', transform=ax.transAxes, fontsize=8)
    metadata.append(dict(case=title, provenance=provenance, parameters=parameters, fit_range=[3.5,67.71], points=curve.GetN(), old_display_error_over_peak=error))
fig.suptitle('Plot the function that was fitted: two pathological cases and two well-resolved controls', fontsize=15)
fig.supxlabel('No refitting or evaluator substitution. Ripple belongs to legacy integration, not the plotter. Shading marks outside the fit window.', fontsize=10)
fig.savefig(a.output / 'fixed-fit-four-case-audit.png', dpi=160)
(a.output / 'fixed-fit-four-case-audit.json').write_text(json.dumps(metadata, indent=2)+'\n')
print(json.dumps(metadata, indent=2))
