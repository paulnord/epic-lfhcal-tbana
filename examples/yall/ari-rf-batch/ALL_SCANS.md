# Combined settings display (plot-only Condor job)

After both the RF and other-settings waveform campaigns finish, use a **new
source checkout** for this helper. Do not update a source directory still used
by running jobs. `prepare_all_scans.py` creates one Condor job; it does not submit.
It only stats inputs and records provenance on the login host. PyROOT reading and
plotting execute inside the existing EIC worker adapter, without compiling or
processing events again.

Native tcsh: first set `OTHER` to the completed other-settings workspace
(the `.../work` directory, not its source or campaign directory). If the original
submission shell still has `B`, use `set OTHER = "$B/work"` before these commands.
Check the original campaign has finished successfully before proceeding.

Create a separate pinned plotting checkout; the code commit below contains both
helpers. No submodule/build is needed for this plotting-only job:

```tcsh
set P = /gpfs01/star/scratch/pnord/ari-all-scans-plots-`date -u +%Y%m%dT%H%M%SZ`
git clone --branch ari-rf-condor-pipeline https://github.com/paulnord/epic-lfhcal-tbana.git "$P/source" && git -C "$P/source" checkout --detach 0ab79ec00f145205b8a7f0763bb030402303265a
set REPO = "$P/source"
set DEST = "$P/work"
```

Only after clone/checkout succeeds, prepare and validate:

```tcsh
python3 "$REPO/examples/yall/ari-rf-batch/prepare_all_scans.py" --rf-workspace /gpfs01/star/scratch/pnord/ari-rf-recovery-20261029T195516Z/recovery --other-workspace "$OTHER" --destination "$DEST" --eic-shell /star/u/pnord/bin/eic-shell
cd "$DEST" && yall-run validate && yall-run plan
```

Expect **one task with 22 waveform histogram inputs** (plus script, run database,
and provenance). After successful preparation/validation, submit explicitly:

```tcsh
set C = `yall-run create --campaigns-dir "$P/campaigns"`
yall-run start "$C"
yall-run status "$C"
```

Stop on any error; do not run `start` after failed `create`. The worker refuses input
size/mtime changes since preparation; unreadable/recovered files, missing or
undersized measurement histograms, noninteger/unknown statuses, and invalid
saved finite measurements fail rather than silently producing plausible plots.

## Contents

`results/HGCROC_AllScans.pdf`, `.png`, and `.root` contain three metric rows
(amplitude, bin-center FWHM, peak-bin time) and four separate scan columns
(RF, CC, CF, CFComp). Each column identifies varied/fixed settings below the plots.
RF codes and their resistance conversion (80/code kOhm) are shown. The RF column
preserves the original 13 selected codes; it does not add recorded codes 2 or 7.

CC varies at RF9/CF7/CFComp1; CF varies at RF9/CC5/CFComp1; CFComp varies at
RF9/CF5/CC5. Existing run298 is reused as the CC/CF baseline. Run355 is shared
between CF and CFComp. CF5 runs355 and363 remain separately labeled repeat
measurements, not pooled or counted as extra channels in one distribution.

The plotter reads `hWaveformPeakAmplitudeVsCellID`,
`hWaveformPeakTimeVsCellID`, `hWaveformFWHMVsCellID`, and
`hWaveformMeasurementStatusVsCellID` written by `HGCROCStudy`. It does not
reimplement waveform extraction or alter timing, clock shifts, fits, or cuts.
The same 64 Ari cells are selected. Widths require successful extraction;
amplitude/time remain available when a peak exists but width extraction fails.
Boxes are interpolated 25th/75th percentiles, center lines medians, whiskers full
included ranges, and dots channels. These describe channel spread, not statistical
uncertainty on a mean. Distinct scan columns have independently scaled vertical
axes, so compare their numerical axes rather than visual box heights alone.

`measurements.csv` retains per-run/per-cell metrics and the original status enum
(-1 means the histogram bin was unfilled). Undefined metrics are blank, not zero.
`inputs.json` records paths, scan grouping, and aggregate quality/boundary counts
from `hWaveformMeasurementStatusCounts`. Those aggregate counts describe the
source histogram's population, not necessarily only the selected 64 cells.
No nonexistent per-cell boundary histogram is assumed or reconstructed.

Local validation uses synthetic ROOT files for all22 distinct inputs and the
real yall loader for the single-task graph. Actual combined scientific results
remain unverified until the new scans complete and the plots are reviewed.
