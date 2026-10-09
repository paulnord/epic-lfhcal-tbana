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
python3 -m unittest test_apply_adaptive_minimal -q
```

The drawing test compiles the actual legacy evaluator from `TileSpectra.cc`.
It uses the cell-896 parameters printed in the earlier diagnostic image
(rounded to six decimals), with no refit or reconstructed experimental data.
On ROOT 6.40.00 the old display interpolation differs from direct evaluation
by up to 52.544% of the peak height. The new 8,428-point curve's midpoint
interpolation error is 0.029% of peak. These quantify display fidelity, not
fit uncertainty or goodness of fit. The test also checks the adaptive callback,
exact bin-center predictions, unchanged fit metadata, and the sampling guard.

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
