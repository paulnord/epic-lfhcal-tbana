# Faithful MIP fit plots

The four MIP plotting helpers previously changed the fitted TF1 range to
0–2000 ADC and drew it with `Npx=1000`, giving about 2 ADC between display
samples. The legacy convolution's 100 integration samples can produce much
finer oscillations when the Landau width is small. Thick, dashed curves and
small layer panels further obscure them. This is display undersampling, on
top of the integration error already present in the fitted objective.

The panels prefer the accepted trigger-selected fit, then the accepted
inclusive fit. `GetSignalModel` hides rejected fits; previously neither a
rejected attempt nor its rejection was displayed. These panels therefore
were not an inventory of every minimization attempt.

`FitCurveDrawing.h` now evaluates the live fitted TF1 into a TGraph. It samples
the visible portion of the original fit range, resolving the Landau width and
the legacy quadrature spacing. Thin, solid lines retain the oscillations;
open markers show predictions at the native histogram bin centers. The
production likelihood fit options omit `I`, so those are the model values
used by the fit, rather than bin-integrated predictions. Connecting samples
uses straight segments, never graph smoothing.

Accepted-fit selection stays unchanged. Rejected attempts are additionally
drawn and labeled orange (triggered) or violet (inclusive). The new diagnostic
accessor returns the last constructed fit; a channel skipped before a TF1
was constructed has no attempted curve. Rejected fits are still excluded
from calibration. An invalid or excessively fine curve gets an explicit
plot warning and log message instead of a misleading coarse line.

The renderer does not alter parameters, fit range, Npx, fit status, fit
likelihood, or calibration. It evaluates whichever callback was fitted:
legacy stays legacy and adaptive stays adaptive. `TileSpectra.cc` is unchanged,
so the adaptive installer can still recognize and patch its exact source.

## Validation

With ROOT and PyROOT available, from the repository root:

```sh
python3 NewStructure/tests/test_fit_curve_drawing.py --figure fit-plotting-audit.png
# Optional compatibility and same-histogram examples, using the header from PR #89:
python3 NewStructure/tests/test_fit_curve_drawing.py --adaptive-header /path/to/AdaptiveLangau.h
python3 NewStructure/tests/compare_fit_curve_samples.py --adaptive-header /path/to/AdaptiveLangau.h --output /tmp/fit-curve-evidence
```

The drawing test compiles the actual legacy evaluator from `TileSpectra.cc`.
It uses the cell-896 parameters printed in the earlier diagnostic image
(rounded to six decimals), with no refit or reconstructed experimental data.
On ROOT 6.40.00 the old display interpolation differs from direct evaluation
by up to 52.544% of the peak height. The new 8,428-point curve's midpoint
interpolation error is 0.029% of peak. These quantify display fidelity, not
fit uncertainty or goodness of fit. The test optionally checks the adaptive callback,
exact bin-center predictions, unchanged fit metadata, and the sampling guard.

## Scope and dependencies

Isolated from historical commit `3c0fdc0` onto upstream `92df3e48`.
No dependency on PRs #86, #87 or #89; no optimizer or evaluator changes.
The optional adaptive test needs the unchanged header from #89, not its build
integration. The seven-parameter fit is drawn using its complete callback,
including pedestal and penalty behavior. The old independently reconstructed
component overlays are omitted: they could select the wrong convolution when
the total fit uses a different evaluator. Noise and correlation plots are unchanged.

The renderer draws only the visible fit window, with no extrapolation. The
center markers are correct for current HG/LG MIP fits, which omit ROOT option
`I`; do not reuse this helper for an `I` fit without implementing its bin-average
prediction semantics. Rejected overlays show the last constructed attempt,
not an archive of all iterations. Sampling a streamed interpolation table is
not a replacement for recovering the original callback.

## Controlled same-histogram examples

[Sample plots](tests/fit-curve-evidence/same-histogram-fit-curves.png) and
[machine-readable counts/results](tests/fit-curve-evidence/same-histogram-fit-curves.json)
retain two predeclared cases, narrow Landau/broad Gaussian and well-resolved
control. Both evaluators fit each identical synthetic histogram with the same
starts, bounds, fit window and `QRLN0S` options. All four fits return status 0
on ROOT 6.40. The narrow legacy fit retains visible finite-grid ripple; both
models agree in the well-resolved control. The data are deterministic adaptive
bin-center expectations, so this is an illustration of numerical/drawing
behavior, **not** an unbiased physical-model benchmark or real beam replay.
No exact current full-chain beam replay is claimed. Each plotted curve calls
its own fitted evaluator, and the shaded regions are outside its fit window.

## Regenerating reports

Rebuild the analysis executable with these plotting changes, then regenerate
the MIP plots and reassemble the report. `assemble_ps_report.py` only collects
existing images; running it alone will not repair old curves. Existing PNGs,
PDFs, and published pages are unchanged by this patch.

The renderer is designed for live fits in the analysis process. A callback
TF1 loaded from a ROOT file may only contain its saved interpolation table.
Increasing Npx or sampling that table densely cannot restore the callback.
To regenerate from saved parameters without refitting, reconstruct the exact
original evaluator and integration method first. Do not substitute the
adaptive convolution for a saved legacy fit. Rejected attempts that were
never saved cannot be recovered from those ROOT outputs.
