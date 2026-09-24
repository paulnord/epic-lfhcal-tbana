# Gaussian-sigma upper-bound experiment

This is an isolated diagnostic. Do not change production calibration bounds
on the basis of a single low-statistics channel.

## Evidence before this experiment

The BNL adaptive fits for cell 903 reached Width approximately 0.1 (lower
bound) and GSigma approximately 29.0645 (upper bound) using both:

- `QRLMN0S`: the saved result reports `Minuit / MigradImproved`.
- `QRLN0S`: the requested default is `Minuit2 / Migrad`.

Removing M changes the backend, not merely an extra Minuit2 step. The no-M
runs returned status 0, fit_valid=1, cov=3, and passed the fixed-parameter
numerical checks, but both retained the two boundary hits and gate=0.
Their reported peaks were 73.36570408 and 73.3609758, not exactly identical
to each other or to the M runs. This supports a common constrained-boundary
solution for these tested starts; it does not prove a unique global optimum.

## Single intended change

`--gsigma-high 58.129` doubles only the Gaussian-sigma upper cap from 29.0645
to 58.129 ADC for this case. It does not change the Gaussian starting value
or lower bound, Landau/MP/area settings, integration accuracy or span, fit
range, data, or minimizer budgets. The effective cap is saved in the existing
`gsigma_high` CSV column and the argv is saved in the ROOT run_context.

No option means the previous cap rules remain unchanged. Invalid, nonfinite,
nonpositive caps or caps that exclude the unchanged Gaussian start are rejected.
`gsigma_override_setup` in CTest exercises the actual parser/setup, checks
unchanged defaults, and verifies that only high[3] changes. Run this ROOT-linked
CTest check with the ROOT build used for the experiment before fitting.

## Run

Use the existing isolated worktree and EIC_SHELL launcher. After fetching this
branch, reconfigure, build and run CTest in fit-study/build. Define the paths:

```tcsh
set TEST = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tbana-delete-test"
set STUDY = "$TEST/examples/yall/hv44-delete-test/fit-study"
set FIT903 = "$STUDY/build/fit_cell903"
set W = "/gpfs01/star/scratch/$USER/lfhcal/hv44-delete-test"
set R903 = "$W/adaptive-refit-20260920T123349Z-va5dbvld"
set H903 = "$W/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_Hists.root"
set C1 = "$W/refine1/rawHGCROC_wPedwMuon_wBC_ImpR_194_calib.txt"
set C2 = "$W/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_calib.txt"
set CAPOUT = `mktemp -d "$W/gsigma-bound-XXXXXX"`

"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 "$FIT903" "$H903" --calib "$C1" --calib "$C2" --integrator adaptive --quad-rtol 1e-10 --fit-option QRLN0 --gsigma-high 58.129 --csv "$CAPOUT/adaptive_sigma58.csv" --results-root "$CAPOUT/adaptive_sigma58.root"

python3 "$STUDY/run_adaptive_refits.py" --show "$R903/adaptive_noM_1e-10.csv" "$CAPOUT/adaptive_sigma58.csv"
```

Compare the adaptive no-M baseline with the new adaptive no-M fit, not with
the fixed-grid objective. Check the returned GSigma against both ceilings,
Width against its unchanged lower bound, objective minimum, EDM, status,
covariance, numerical verification, and agreement between seeds.

A stable interior GSigma above the old cap would support that the old cap
constrained this fit. The Landau-width bound may remain active. A new ceiling
hit, inconsistent seeds, or failed diagnostics calls for further investigation,
not automatic acceptance. Raising the cap alone does not establish model
adequacy, trustworthy boundary errors, a corrected calibration, Fredi's procedure,
or a ROOT bug. Production-to-standalone differences remain unresolved.

## Local comparison using a transferred result histogram

The launcher can run both no-M cases in separate processes, using a saved
`source_histogram` directly. From the repository root, with an existing local
ROOT/compiler installation:

```sh
cmake -S examples/yall/hv44-delete-test/fit-study -B build-mac
cmake --build build-mac -j2
ctest --test-dir build-mac --output-on-failure
ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 python3 \
  examples/yall/hv44-delete-test/fit-study/run_adaptive_refits.py \
  --fitter build-mac/fit_cell903 \
  --calib local-data/refine1/rawHGCROC_wPedwMuon_wBC_ImpR_194_calib.txt \
  --calib local-data/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_calib.txt \
  --experiment gsigma-bound \
  --histogram local-data/adaptive-refit-20260920T123349Z-va5dbvld/adaptive_noM_1e-10.root \
  --histogram-key source_histogram \
  --out local-results/gsigma-bound-new
```

`--out` is required for this experiment and must name a new directory. The
baseline uses `QRLN0` and adaptive rtol 1e-10; the second case adds only
`--gsigma-high 58.129` to the scientific controls. Both use the same two
calibration files and histogram. The existing three-case integration study
remains the launcher's default. CSV validation rejects malformed or truncated
rows before launching a subsequent case; failures preserve completed outputs.
CTest also includes the existing fixed-width controls and Python runner tests.
The input ROOT file, calibrations and executable are hashed; per-case UTC
timestamps and elapsed seconds are recorded. `--work` remains supported for
the original layout when explicit calibration paths are omitted.

Compare each local row with its corresponding local baseline before comparing
hosts. A saved histogram permits this isolated refit but does not recreate
the full production event loop or all in-memory production calibration inputs.
