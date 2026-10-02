LFHCal validation on previously unused control spectra

Input: fit-range-controls-20261002.zip (32 run/cell cases, 64 histograms).
Verify the ROOT SHA256 and all 493 copied context/source file hashes from the
manifest before analysis. Compare selection against range-control-selection.json.
The original 40-spectrum study was used to develop the rule; these 64 spectra
were not used to tune it. The same cell can be paired between B1 and B2, so
these are not 64 independent detector channels.

Selection is deliberate, not random: one original-method agreement control
per layer in B1, E1 and E2 (24 run/cell cases), plus eight B2 counterparts.
Require both original fits saved, BC>=2, H inside their windows and reported
legacy/adaptive H agreement within 1%; choose median entry count per layer.
Exclude all previously studied cell IDs. B2 is not screened by fit agreement.
Two B2/199 spectra have no saved fit; both original rejections are reproduced.

Frozen fitting rule: Gaussian smoothing with sigma=2 original bins only for
range finding. Locate the prominent expected peak and a resolved lower valley
using the original study's cuts. Lower edge=max(original lower edge, valley).
Fit original bins with the archived adaptive convolution. Retain the original
upper edge and production starts/parameter bounds; recompute the area seed and
upper bound from the selected interval as production does. No parameter was
tuned on this control bundle and no best-of-optimizer fallback is applied.
No usable valley means no proposed change; diagnostic scans are still shown.

832 fits:
128 original-method baselines (raw errors and finite empty-bin errors);
64 adaptive-evaluator fits over the original window;
64 production-budget candidate fits;
576 nearby-boundary trials (9 per histogram).
The intermediate adaptive/original-window fits separate convolution-evaluator
changes from range changes. H is the continuous convolution peak, not Landau MPV.

Boundary protocol matches the initial test: radius=max(2 bin widths,5% observed
peak), lower offsets [-2,-1,-0.5,0,0.5,1,2]. Primary neighborhood is [-1,1].
Two separate upper-edge tests use +/-10% of the original upper edge. Fixed
1000-call/100-iteration budget, QRLMN0S, IMPROVE seed 12345. Do not interpret
scan ranges as statistical confidence intervals or universal tolerances.

ROOT runtime 6.40.00; input extraction 6.40.04. For 62 saved fits, original
parameters are reproduced to max scaled difference 1.78e-5, where scaling is
max(abs(saved parameter),1). The two spectra without any saved TF1 (B2/199)
use the pedestal sigma from the six-decimal previous calibration table. All
others recover its full precision from stored TF1 bounds. Both missing-fit
cases still hit the Gaussian-sigma bound. They are diagnostic exceptions,
not validated normal controls. Inputs remain unchanged; only working clones
replace nonfinite empty-bin errors by zero. All 53,805 nonfinite-error bins
are empty; no occupied-bin errors are affected.

Reports: one run/cell case per page, with each histogram population shown.
All curves use the adaptive evaluator. Dotted parts of curves are extrapolated
outside the fit range. Plot height focuses on the MIP region and may clip the
pedestal. Red X on scans marks rejected fits or peaks outside the fit window.
Summary extrema retain all trials, including rejected ones. The peak-core
Poisson deviance per bin compares identical bins from 0.7 to 1.6 times the
observed smoothed peak; it is a diagnostic, not reduced chi-square or a p-value.

Reproduction (Python environment with PyROOT, NumPy, SciPy and Matplotlib):
python3 run_fit_range_study.py --bundle INPUT --out RESULTS/baseline-b1 --phase baseline --datasets b1
python3 run_control_validation.py --bundle INPUT --out RESULTS --dataset b1
Repeat these two commands for b2, e1 and e2 with corresponding output names.
Then:
python3 analyze_control_validation.py --bundle INPUT --results RESULTS
Required helper: test_boundary_stability.py, plus the scripts above, all from
paulnord/epic-lfhcal-tbana branch codex/adaptive-langau-minimal.

No production calibration is updated. No event-level recalibration or detector
response test is included. The sample cannot estimate detector-wide failure
rates; those require an independently drawn sample and eventual event replay.
