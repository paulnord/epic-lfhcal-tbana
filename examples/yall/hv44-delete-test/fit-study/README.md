# Cell 903 isolated MIP-fit study

This ROOT-only program reads an existing histogram without the LFHCal event
loop. It copies the Landau-Gaussian function, improved-fit setup, and legacy
peak/FWHM search for a numerical investigation. It is not a validated replacement
calibration procedure.

## What is established

For the user's run-194 cell-903 test, refine2 and refine3 had identical histogram
bin counts (127 entries), and ran on the same host and Condor slot. Their stored
fit parameters nevertheless differed. The standalone program has **not** yet
reproduced those production fits: its first two tests hit the Gaussian-width
upper limit. The production-to-standalone difference remains unresolved.

A separate fixed-parameter check, `check_convolution.C`, demonstrated strong
integration-resolution dependence using the actual ROOT functions in the EIC
environment. No histogram or minimizer was involved in that check:

| Fixed parameter set | FWHM at np=100 | FWHM at np=1000 | FWHM at np=10000 |
| --- | ---: | ---: | ---: |
| production refine2 | 2.78582495045 | 66.5208613246 | 66.5208613754 |
| production refine3 | 1.88612870623 | 64.4497267476 | 64.4497506292 |
| standalone seed1 | 2.91561682758 | 70.0773835367 | 70.0773835296 |

The function values themselves changed substantially between np=100 and the
denser grids, not just the derived FWHM. These are numerical-resolution tests
at fixed parameters, **not corrected calibrations or evidence of a Minuit bug**.
Agreement at a few coordinates does not establish integration accuracy over
the full fit-parameter domain. The existing peak search is also still used;
for production refine3 its peak changes by about 0.00521 ADC between np=1000
and np=10000 despite close FWHM agreement.

The immediate next experiment is a resolution study of the standalone refits,
separate from the still-unresolved production reproduction.

## Build in the EIC environment

Use the isolated test worktree. Do not rebuild the production checkout.
`EIC_SHELL` must already identify the workspace's EIC-shell launcher.

```tcsh
set TEST = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tbana-delete-test"
set STUDY = "$TEST/examples/yall/hv44-delete-test/fit-study"
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" cmake -S "$STUDY" -B "$STUDY/build"
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" cmake --build "$STUDY/build" -j2
set FIT903 = "$STUDY/build/fit_cell903"
```

## Compare integration resolutions

`--steps N` changes the even integration-step count for **both fitting and
post-fit peak/FWHM calculation**. The default is still 100. The +/-5 Gaussian
sigma integration interval, parameter starts/limits, fit range rules, ROOT fit
options, and minimizer call/iteration budgets are otherwise unchanged for
these commands.

`--csv FILE` writes a dedicated CSV file rather than mixing ROOT console output
into it. It refuses an existing readable file; use a new result directory for
another experiment. The program returns zero when it completed recording the
fits, even when a recorded fit would fail the legacy acceptance gate.

```tcsh
set W = "/gpfs01/star/scratch/$USER/lfhcal/hv44-delete-test"
set H903 = "$W/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_Hists.root"
set C1 = "$W/refine1/rawHGCROC_wPedwMuon_wBC_ImpR_194_calib.txt"
set C2 = "$W/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_calib.txt"
set STAMP = `date +%Y%m%d-%H%M%S`
set OUT903 = "$W/fit-resolution-$STAMP"
mkdir -p "$OUT903"

"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 "$FIT903" "$H903" --calib "$C1" --calib "$C2" --steps 100 --csv "$OUT903/np100.csv"
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 "$FIT903" "$H903" --calib "$C1" --calib "$C2" --steps 1000 --csv "$OUT903/np1000.csv"
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 "$FIT903" "$H903" --calib "$C1" --calib "$C2" --steps 10000 --csv "$OUT903/np10000.csv"
```

Inspect fit parameters as well as peak/FWHM. Agreement of two seeds is not by
itself proof of a globally optimal fit. Check resolution stability, the actual
fit status, boundary flags, and peak-search status before broader scans.

The first 37 CSV columns retain their previous order. `valid` remains an alias
for `TF1::IsValid()` only, not minimization validity. `peak`, `fwhm`, and
`langau_status` refer to the legacy peak search. Three columns are appended:

- `np`: the integration-step count used throughout this invocation.
- `limits_reached`: number of fitted parameters within 1e-5 of either bound.
- `legacy_fit_gate_pass`: TF1 validity, historical status-code acceptance
  (0, 4000, 70, 4070), and zero boundary hits. This mirrors only the post-fit
  gate in `FitMipHG`, not its earlier bad-channel/signal-to-noise skips, and
  does not certify reliable errors, convergence, or numerical accuracy.

Output precision is now 17 significant digits. This changes printed precision,
not the fit calculation. The historical ROOT fit option `QRLMN0` is retained
for the first resolution comparison. Do not interpret status 4000 as an
unqualified success simply because the legacy code accepts it.

## Remaining reproduction details

The defaults are specific to the observed run-194 case: cell 903, pedestal sigma
0.581290, Vov 5.7 V, and the more-than-five-layers branch. `--layers 8` selects
that branch; it is not a measurement of the actual segment geometry.

`--calib` averages the exported rows with ScaleH != -1000 and BC >= 2. It
assumes BC filtering is enabled and does not emulate loading a ROOT calibration
and applying `ReadCalibFromTextFile`'s 1e-4 conditional overrides. The text
pedestal sigma is also rounded. Therefore `--calib` is not proof of bitwise
identity with all effective in-memory production inputs.

The convolution/peak-search functions remain copies of application code.
Compiler flags, ROOT build, runtime settings, and the state of prior fits still
need checking when reconciling the standalone and production results.

## Later controlled tests

`--fit-low`, `--fit-high`, `--start-mp`, `--mp-low`, and `--mp-high` permit separate
control of fit-window and MP starting/boundary effects. `--repeat` repeats a seed
in the same process; separate invocations are needed for fresh-process tests.
`--scan 52.00 52.20 0.001` is available, but first establish numerical resolution.

For a CPU comparison, use the same executable, libraries/container, histogram,
inputs and settings on both hosts, and preserve the runtime provenance. The
present resolution check does not establish an AMD/Intel effect.
