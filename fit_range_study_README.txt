LFHCal frozen-histogram fit-range study, 2026-10-01
================================================

This is an exploratory study driver, not a production calibration change.
It uses the original-bin spectra and archived C++ evaluators extracted by
pack_fit_range_study.py. The fit always runs in ROOT. SciPy is used only to
locate a peak and valley in a temporary smoothed copy; it does not fit data.

Scripts in codex/adaptive-langau-minimal:
  run_fit_range_study.py       ROOT fits and controlled range candidates
  analyze_fit_range_study.py   all-fit CSV/JSON, overlays, lower-bound scans
  make_fit_range_report.py     three-page result/method report
  fix_empty_bin_systematics.patch  proposed independent NaN-error fix

Requirements:
  Python 3, PyROOT, NumPy, SciPy (candidate phases).
  Matplotlib (analysis and report), ReportLab (report).
  Tested with ROOT 6.40.00. Input production ROOT was 6.40.04.

Input:
  fit-range-study-inputs-20261001-v2.zip, extracted to a directory containing
  manifest.json, histograms.root, context/, campaigns/.
  These selected spectra are not an unbiased sample or held-out validation set.
  The scripts are intentionally specific to this bundle's 5/10-layer setup;
  reconstructed ranges and limits are checked against every available saved fit.
  Full-precision pedestal sigmas and dataset averages are recovered from saved
  parameter limits/ranges and checked against the preceding calibration text.
  A missing fit uses the matching cell's other-method pedestal sigma.

Study layout and reproduction (tcsh, from a directory with the scripts):

set BUNDLE = /gpfs01/star/scratch/pnord/lfhcal/fit-range-study-inputs-20261001-v2
set STUDY = /gpfs01/star/scratch/pnord/lfhcal/fit-range-study-check-20261001

python3 run_fit_range_study.py --bundle "$BUNDLE" --out "$STUDY/seeded-baseline" --phase baseline
python3 run_fit_range_study.py --bundle "$BUNDLE" --out "$STUDY/scan-b1" --phase scan --datasets b1
python3 run_fit_range_study.py --bundle "$BUNDLE" --out "$STUDY/scan-b2" --phase scan --datasets b2
python3 run_fit_range_study.py --bundle "$BUNDLE" --out "$STUDY/scan-e" --phase scan --datasets e1 e2
python3 run_fit_range_study.py --bundle "$BUNDLE" --out "$STUDY/candidate" --phase candidate
python3 run_fit_range_study.py --bundle "$BUNDLE" --out "$STUDY/production-candidate" --phase production_candidate
python3 analyze_fit_range_study.py --bundle "$BUNDLE" --study "$STUDY"
python3 make_fit_range_report.py --study "$STUDY"

At BNL, prefix each Python command with the existing EIC wrapper if ROOT is
not available in the current shell:
  /gpfs01/star/scratch/pnord/lfhcal/adaptive-fullchains-20260928T223211Z/run-in-eic-shell.sh
  ~/my_eic_work_with_LFHCAL/eic-shell
Those two paths and the python3 command must be on the same command line.
The candidate phase also requires SciPy in that Python environment.
The scan partitions can run independently. No Condor submission is performed.

Fit phases:
  baseline: 80 fits, original and finite empty-bin errors for all 40 inputs,
    original evaluator per population, 1000 calls / 100 iterations.
  scan: 320 fits. Adaptive evaluator on both populations; original range,
    nominal geometry-based floor, and lower floors 0.30, 0.45, 0.60, 0.75,
    0.90, 1.05 times the dataset-average MIP scale. Floors never lower the
    original boundary. Original starts/limits and upper edge are fixed.
  candidate: 120 fits. Same fixed setup, valley detection with smoothing
    sigmas 1.5, 2 and 3 bins. No optimizer best-of selection.
  production_candidate: 40 fits. Central valley rule, original 1000-call /
    100-iteration budget; area seed and limit recalculated from new range.
  scan/candidate use a uniform 10000-call / 1000-iteration budget. Every fit
    starts independently. QRLMN0S invokes Minuit / MigradImproved; the IMPROVE
    seed is reset to 12345 for each fit. Original production RNG history is
    not available; local baseline nevertheless reproduces all 37 saved fits.

Output and interpretation:
  Each completed fit is appended to JSONL; reruns resume by its unique key.
  Changing recorded environment/settings requires a new output directory.
  Input ROOT files are read-only. No calibrations are updated.
  all-fit-results.json/CSV contains the 520 controlled trials; production-
    candidate JSONL and production-validation.json contain the extra 40 checks.
  For legacy evaluations, smooth_peak is the peak of the ADAPTIVE continuous
    convolution at those parameters, NOT legacy's stepping-algorithm H.
  Overlay/scans compare adaptive fits on both histogram populations. The
    separate E2 evaluator figure shows the saved legacy numerical wiggles.
  Flags in range_rule distinguish a usable valley from a baseline retained
    because no suitable peak/valley was found. This is not an auto-rescue rule.
  Passing production numerical checks is not a quality or physical-validity test.
  Never adopt a fitted H that lies outside the fitted interval without review.
  Common-core Poisson deviance is evaluated on identical bins across variants:
    0.7 to 1.6 times the observed smoothed peak. It is a diagnostic, not a p-value.
  Large absolute deviances persist from data bin structure and model mismatch.

NaN-error patch:
  Archived Analyses.cc forms a relative uncertainty by dividing by bin content.
  Empty bins become NaN. The supplied patch replaces that expression with
  std::hypot(old_error, 0.15*content), preserving occupied-bin uncertainties.
  It is a proposed patch against the archived source, not automatically applied.
  Fixing this does not add a 15% systematic model to the Poisson L objective.

Study results:
  Smoothed-valley ranges substantially improve B2 cells 263, 775, 1478, 1991
  and E1 cell 1223. Clean B1 controls remain close; broader B1 cases shift by
  up to 4%, so validate on additional cells before a full-chain deployment.
  B2/67 stays flagged; B2/706 barely changes; E2/1344 retains a bin-structure
  mismatch. See the accompanying report and full per-cell overlays.
