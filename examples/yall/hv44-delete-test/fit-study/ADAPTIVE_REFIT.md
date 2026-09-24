# Adaptive convolution inside the isolated fit

This is a controlled experiment, not a replacement calibration. Production
code, parameter bounds, fit-range rules, histogram selection, and the previous
fixed-width diagnostic are unchanged.

## Experiment

`fit_cell903 --integrator adaptive` evaluates the model during every fit call
using the **unchanged** `fixed_width::Convolution` in `fixed_width_numerics.h`,
the evaluator exercised by `check_fixed_widths.C`. ROOT's standard Landau density
and the original +/-5 Gaussian-sigma integration interval are retained.
`--quad-rtol` controls the adaptive tolerance (1e-8 by default).

The original fixed-grid mode remains the default. The launcher runs these cases
on the same refine2 histogram and with the same two previous-calibration seeds:

1. Fixed grid, 100 steps, as a control.
2. Adaptive integration, relative tolerance 1e-8.
3. Adaptive integration, relative tolerance 1e-10.

Each case runs in a fresh process and fits two seeds in the same order. No seed
scan, change of bounds, or integration-window widening is performed. The
1000-function-call/100-iteration budgets and Minuit2/Migrad choice are retained.
The actual TH1 fit options are `QRLMN0S`: only `S` is added, to retrieve the full
fit result. The fixed-grid control uses it too. We do not reinterpret the
historically accepted nonzero status codes as unconditional success.

For adaptive runs, the fitted parameters are then held fixed and checked with
integration tolerances rtol and rtol/100, bracketed peaks and half-height roots.
The checks include the prior 129-coordinate curve survey and bin centres inside
the fit range. A separate +/-8 sigma evaluation reports cutoff sensitivity; it
is not substituted into the fitted model. The numerical implementation, finite
sampling limitations and empirical error estimates remain those documented in
`FIXED_WIDTH_CHECK.md`.

## Run on BNL

Use the isolated test worktree and the workspace EIC-shell launcher. Only the
standalone study is rebuilt. These commands do not rebuild `DataPrep`.

```tcsh
set TEST = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tbana-delete-test"
set STUDY = "$TEST/examples/yall/hv44-delete-test/fit-study"
git -C "$TEST" fetch origin test/array-delete-hv44
git -C "$TEST" merge --ff-only FETCH_HEAD
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" cmake -S "$STUDY" -B "$STUDY/build"
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" cmake --build "$STUDY/build" -j2
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" ctest --test-dir "$STUDY/build" --output-on-failure
```

After the build and control test succeed:

```tcsh
set W = "/gpfs01/star/scratch/$USER/lfhcal/hv44-delete-test"
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 python3 "$STUDY/run_adaptive_refits.py" --work "$W"
```

The launcher creates a new `adaptive-refit-...` directory inside W and prints
its path. An explicit `--out DIR` is also supported, but DIR must not exist.
It never overwrites earlier CSVs, ROOT inputs or calibrations. Each case has a
CSV, console log, and ROOT result file. A run.json records commands, exit codes,
hashes of the executable, calibration texts and input ROOT file, histogram
path/stat data, and per-case UTC timestamps and elapsed seconds. Each result
file contains the actual input TH1 under `source_histogram`.
ROOT/compiler/host and argv are also recorded. Earlier BNL manifests omitted
the ROOT-file hash; they are preserved as originally produced.

A nonzero subprocess exit stops the launcher and preserves partial outputs.
Zero exit means the fits were recorded, **not that they were accepted**. A
quadrature failure during minimization aborts the invocation rather than
silently returning an arbitrary penalty. A post-fit curve-check failure is
recorded with a message and numerics_pass=0; it does not erase the fitted result.

## Output and compatibility

The original first 40 CSV columns remain in their original order. In fixed-grid
mode their interpretation is unchanged. For an adaptive fit, `np=0` denotes no
fixed integration grid, and legacy `langau_status=-99`, `peak=nan`, `fwhm=nan`
mean the legacy width search was deliberately **not run**. The new bracketed
results are in `adaptive_peak` and `adaptive_fwhm`; they are not silently written
into the legacy columns.

Appended columns include:

- `fit_options_effective`, `result_present`, `result_valid` (TFitResult validity),
  `min_fcn`, `edm`, `n_calls`, `cov_status`, and `minimizer_type`.
- Named boundary hits in `boundary_parameters`.
- Adaptive peak, crossings, FWHM, half-height fractions, tighter-tolerance and
  integration-span comparisons, and `numerics_complete/pass/error`.
- `result_key`, ROOT version, compiler, execution host and fit budgets.

`valid` still means TF1 validity only. The historical `legacy_fit_gate_pass`
is not a substitute for fit-result or numerical diagnostics. `numerics_pass`
checks the frozen returned curve only. It neither certifies fit optimality nor
turns a boundary-rejected fit into an accepted calibration.

`--results-root FILE` saves the full TFitResult objects, including covariance,
as `fit_result_1`, `fit_result_2`, etc. Match them to the CSV's `result_key`.
This preserves fit metadata; reloading does not promise an evaluable serialized
callback function. Re-evaluate curves with the parameter columns and this code.

Summarize saved results again without ROOT:

```tcsh
python3 "$STUDY/run_adaptive_refits.py" --show /path/to/fixed100.csv /path/to/adaptive_1e-8.csv /path/to/adaptive_1e-10.csv
```

The summarizer reads column names and preserves NaNs; it does not use positional
awk numeric conversions. Compare fitted parameters between tolerance runs,
not just the post-fit numerics_pass flag. The standalone-to-production mismatch
and uncertainty about the historical reference procedure remain unresolved.

## Validation before BNL

The shared numerical header was verified byte-for-byte against its previously
validated GitHub blob (8140f53fbb1057e22253bac0f904619ca78c1646). Its 24 analytic
controls pass, as do two new post-fit tolerance controls and an invalid-vector/
NaN-preservation check. Four Python orchestration/reporting tests pass using a
clearly labelled mock process, not a ROOT minimizer. The baseline convolution,
legacy search, calibration parser and fit-setup routines were checked unchanged.

The new ROOT-linked executable and actual cell-903 refits have **not** been run
in the development environment. The BNL build and scientific run are therefore
the next validation steps; no adaptive fitted calibration values are claimed.
