# Full-chain test of the valley boundary

This test rebuilds **Legacy and Adaptive** with the same frozen boundary finder.
It runs B1, B2, C1, C2, C3, D1, D2, E1, E2, E3, F1, F2, G1 and G2 through R5,
then continues B2 through R8. The 233-task Condor DAG includes separate builds,
14 shared pre-MIP inputs, 28 chains, 14 comparisons, and a summary.

Existing original-boundary campaigns supply the other two arms of the four-way
comparison. Their reports are copied and fingerprinted; their sources, binaries,
ROOT files and calibrations are not modified. D1 uses its successful recovery
campaign, and B2 R6-R8 uses its extension campaign.

## Scope of the code change

The preparation script applies `apply_mip_range.py` to two **new source snapshots**
from the original campaigns. It refuses unfamiliar TileSpectra source hashes.
The regular checkout is not the source of either fitter's production snapshot.

The shared C++ header is `NewStructure/MipRangeFinder.h`. Its fixed rule is:

* Smooth a temporary count vector with Gaussian sigma=2 bins, truncation=4,
  reflected edges. Fit the original histogram bins.
* Find peaks separated by at least 8 bins, with prominence >=20% of the maximum
  smoothed count in [max(3 pedestal sigma, 0.5 average MIP), 2.5 average MIP].
  Choose the most prominent qualifying peak. Distance pruning precedes prominence;
  equal-height distance ties choose the rightmost peak deterministically.
* Find the minimum between 3 pedestal sigma and 0.8 observed peak. Require an
  interior minimum and valley height <=50% of the peak height.
* New lower edge=max(original lower edge, valley), retaining the original upper
  edge. No usable valley means retain the original edge and log the reason.

It applies only to HG HGCROC **refinements** (`impE=true`). The initial MIP pass
has no refinement average and keeps the original rule. CAEN/LG are unaffected.
The original area initialization follows the updated range, as in the study.
MPV bounds, fit options, parameter limits other than the range-derived area,
error construction, convolution evaluator, peak extraction and fit acceptance
remain as in each original method. This change does not repair Legacy's known
convolution oscillations. The separate empty-bin error patch is not applied.

`LFHCAL_RANGE_V1` records the old/new edge, observed peak, valley, depth, and
reason for every attempted refinement fit. Auditing verifies that any saved
TF1 range equals the logged decision. An unavailable valley is an explicit
flag, not a new optimizer fallback or a scientifically accepted fit.

## BNL preparation (tcsh)

```tcsh
set REPO = ~/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark
set RANGEWORK = /gpfs01/star/scratch/pnord/lfhcal/boundary-fullchains-20261002

git -C "$REPO" fetch origin codex/adaptive-langau-minimal && \
git -C "$REPO" show FETCH_HEAD:prepare_boundary_fullchains.py > /tmp/prepare_boundary_fullchains.py && \
python3 /tmp/prepare_boundary_fullchains.py --repo "$REPO" --ref FETCH_HEAD --out "$RANGEWORK" && \
cd "$RANGEWORK" && \
yall-run validate && \
yall-run plan > plan.txt
```

Preparation resolves FETCH_HEAD to a commit, retrieves all helper files from
that same commit, and records their hashes. It verifies original sources,
recipes, successful reference stages, transfer-file metadata, ROOT versions,
and the EIC shell. It refuses an existing output directory. No jobs are submitted.
The input jobs hash the original pre-MIP ROOT data on workers and open it read-only.
No selected-event file is substituted for the initial calibration input.

To create and start the prepared test, capturing the campaign path automatically:

```tcsh
cd "$RANGEWORK" && \
set RANGECAM = `yall-run create --campaigns-dir "$RANGEWORK/campaigns" | tail -n 1`
yall-run start "$RANGECAM" && yall-run status "$RANGECAM" -v
```

The full plan is `$RANGEWORK/plan.txt`. Fit jobs have an 8-hour internal timeout
and 10-hour Condor wall-time request; builds request 4 CPUs/2 hours. All fitting
stays single-threaded. Source/binary hashes and the original ROOT version are
checked; build checks run before dependent tasks. The full event run and actual
production builds happen on BNL, not in the local frozen-histogram environment.

## Results to inspect

* `all-stage-statistics.csv`: four-way saved, available, carried-forward,
  selected entries, mean H, boundary status counts, and timing by stage.
* `all-cell-boundary-comparisons.csv`: each evaluator's original/new H, widths,
  fit parameters, selected entries, fit presence, range status, and H change
  from the previous refinement.
* `reports/<set>-four-way-stages.json`: original/new stage summaries.
* `reports/<set>-comparison.csv`: new Legacy versus new Adaptive, compatible
  with the previous comparison layout.
* Each fit stage retains `cells.csv`, `range-audit.json`, ROOT outputs and plots.

Changed calibrations can affect later selection and convergence. Review those
trajectories and spectra before accepting a production calibration change.
Successful minimization, or more saved fits, is not itself scientific approval.

## Verification completed before publication

* C++ rule agrees with the frozen SciPy study on all 104 uploaded histograms:
  identical usability decisions and lower edges, and agreement of available
  peak/valley/depth diagnostics within 1e-12.
* Both patched TileSpectra translation units pass syntax compilation with ROOT
  6.40.00 headers. Production builds require the original BNL ROOT version.
* Standalone C++ checks cover the numerical valley, unchanged input counts,
  retained floors, invalid input and absent-peak behavior.
* A synthetic campaign fixture validates the actual 233-task Yallfile and
  four-way report joins; originals remain unchanged and overwrite is rejected.
* A ROOT fixture verifies boundary diagnostics, carried-forward counts, and
  rejection of a saved-fit/logged-edge mismatch.
