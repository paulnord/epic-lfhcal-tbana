# Native waveform annotations: BNL handoff

**Prepared, not run at BNL.** This extends PR #21 on
`paulnord/epic-lfhcal-tbana`, branch `ari-rf-condor-pipeline`. It adds plotting
inside `HGCROC_Waveform_Analysis::AnalyseWaveForm`, using the `TileSpectra`
measurements already computed there. No separate ROOT macro or PyROOT is needed.

## Get the updated source safely (host tcsh)

Use a fresh shared-storage checkout containing this change. Set `BASE` to a new
workspace visible on the submit host, execute nodes and inside the EIC container:

```tcsh
git clone --branch ari-rf-condor-pipeline --recurse-submodules https://github.com/paulnord/epic-lfhcal-tbana.git "$BASE/source"
set REPO = "$BASE/source"
git -C "$REPO" status --short
git -C "$REPO" rev-parse HEAD
ls "$REPO/NewStructure/WaveformAnnotations.h"
```

Stop on any error or if the new header is absent. Record the source SHA with the
results. Do not switch branches, pull, reset, clean or rebuild a checkout used
by an active campaign. Preserve existing uncommitted changes and old outputs;
a fresh checkout avoids disturbing either. Keep the new source/configuration
and inputs immutable from preparation through completion. Existing campaigns
retain archived wrappers, so prepare a fresh campaign after updating the code.

Follow the existing [Ari RF batch guide](README.md) for pilot preparation and
review of the recovered analysis recipe. Host work is limited to setup,
provenance, validation and explicit submission/monitoring. **Do not compile,
run ROOT, test or analyse events on the login host.** Submit from normal host
tcsh, not an interactive EIC shell. This handoff does not submit anything.

## Build and test on the existing Condor worker

The existing `build.sh` adds target `test_waveform_annotations` and CTest test
`waveform_annotations` alongside `waveform_measurement` and
`fit_curve_legend_lifetime`. The normal build node compiles the executables and
runs these tests before downstream analysis. Keep its pinned decoder submodule,
`BUILD_TESTING=ON` and `LFHCAL_USE_ADAPTIVE_LANGAU=OFF` settings.

The following is **worker-only tcsh**, inside the established ROOT/EIC runtime,
with `REPO` and `BUILD` resolved to the fresh campaign's source/build paths.
The existing `worker.sh` supplies `ARI_RF_BATCH_WORKER=1`; do not set it manually
to bypass the login-host guard:

```tcsh
/bin/bash "$REPO/examples/yall/ari-rf-batch/build.sh" "$REPO" "$BUILD" "$BUILD/READY"
```

Stop on failure and inspect the build log. A local synthetic-test pass is not
evidence that BNL mounts, production ROOT or detector inputs were verified.

## Use the same native waveform command

No new analysis option is required. The existing waveform DAG node already uses
`-w -E 1 -l activeCellsHGCROCParameterScan.txt`. For a worker-side invocation,
resolve `BUILD`, `INPUT`, `OUTPUT`, `PLOTS`, `RUNDB` and `CELLS` from that node's
actual expanded command. `INPUT` is its calibrated event ROOT file, not an old
`_Hists.root` file. `RUNDB` is the May 2026 run database; `CELLS` is the existing
active-cell list. Use a fresh output ROOT path and plot directory:

```tcsh
"$BUILD/HGCROCStudy" -d 1 -E 1 -w -i "$INPUT" -o "$OUTPUT" -O "$PLOTS" -r "$RUNDB" -l "$CELLS"
```

Do not add `-f`, an event limit, new cuts or different calibration options.
The normal prepared DAG supplies these paths automatically. No retrieval or
reconstruction of old ROOT profiles is required; annotations are produced as
part of native waveform analysis.

## Products and checks

Under the waveform task's plot directory, each run gains:

- `WaveformGrid_Run<run>_Original.pdf`
- `WaveformGrid_Run<run>_Annotated.pdf`
- `WaveformGrid_Run<run>_Measurements.csv`

The paired PDFs use matching channel order, axes and pagination, with up to 64
channels per page. Existing `Waveform_*` products remain unchanged. Compare each
original page with its annotated counterpart. Each 64-cell block now has four
pages, in this order:

1. Absolute profiles with a shared y-axis **within each layer column**. This is
   the original absolute-page position with the requested scale change.
2. Profiles normalized by each cell's supplied peak, retaining the original
   normalized-page position and fixed -0.08 to 1.12 y-range.
3. Absolute profiles with a robust, per-layer upper range and explicit outlier
   and clipping labels. This is an additional display, not a data selection.
4. Absolute profiles with the full global search-window range, retaining the
   former global-scale view for comparison and amplitude auditing.

For the Ari 64-cell selection, column headers are the zero-based cell-ID layer
indices, ascending left to right. Rows are ascending `(module, row, column)`
positions; the current list produces rows M2/r0/c2, M2/r0/c3, M2/r1/c2, M2/r1/c3,
M3/r0/c0, M3/r0/c1, M3/r1/c0 and M3/r1/c1. Every pad retains its cell ID. This
layout is derived from the IDs even if the input list is shuffled. It is enabled
only for the complete Cartesian product of eight layer indices and eight
positions. Other selections keep input order and global absolute scaling with
an explicit irregular-selection note, rather than inventing geometry columns.
The CSV preserves its original input order and contains the same measurements.

These headers describe encoded readout layer/segment indices, not equal physical
depths or verified installed wiring. The May nominal sumV2 map has 5-layer sums
at indices 0-3 and 10-layer sums at indices 4-7; no division by those counts is
introduced. Module/row/column labels require no assumed ASIC mapping.

### Robust view and clipping

The robust page calculates a separate upper Tukey fence `Q3 + 1.5 * IQR` for
each layer's supplied positive finite peak amplitudes. Quartiles use unbinned
linear `q * (n - 1)` interpolation. With at least four peaks, a peak strictly
above the fence is omitted **only from upper-range calculation**, together with
that cell's positive profile samples. Equality is retained. With fewer than four
peaks, the ordinary full layer range is used. A zero IQR retains equal peaks and
can flag a larger one. With only eight cells per layer, multiple extremes may
mask each other; this is a display aid, not a channel-quality decision.

All cells' negative search-window excursions remain in the lower-range
calculation. Every profile and measurement stays present; finite peaks with
unavailable FWHM remain eligible. Purple arrows indicate actual clipped trace
values, accompanied by the extreme displayed value and the unchanged measured
peak `A` in ADC units. The separate `high peak: scale only` label identifies
upper-range exclusions, even if padding happens to keep that peak on screen.
Clipping and statistical flags are distinct: post-search noise can also clip in
the full-range and normalized views. No off-scale amplitude guide is drawn at
an invented boundary value. The full global companion shows all measured peaks.

Fixed-TOA selections use the existing `nTOA_<sample>` subdirectory. Absolute
scaling, like the saved 64-cell producer, excludes samples after the bin
containing 200 ns so late noise does not flatten the pulses; late values can
therefore extend outside the displayed y range.
For an on-scale valid measurement, annotations contain exactly three vertical guides
(left width endpoint, peak time, right width endpoint) and one horizontal
peak-amplitude guide. Invalid widths omit the width guides, rather than
inventing a zero width; measurement/status values remain available in the CSV.
An off-scale peak omits the horizontal amplitude guide and uses the distinct
clipping marker/numeric peak label instead. The timing and width guides are not
repositioned or remeasured.

This is a display/export addition: **zero new fits, cuts, waveform extractions,
or changes to timing or baseline conventions**. It reuses Ari's peak-bin timing
and bin-center width endpoints, including existing invalid-measurement flags.
Check the worker test log, paired PDFs and CSV before extending the pilot.
An annotation/export failure is logged as a warning so the normal histogram
output is still saved. Check that all three new files exist and that both PDFs
open fully; overall analysis success alone does not establish report completion.
No BNL build, analysis run or submission was executed for this handoff.

## Existing parameter scans: waveform-only campaign

Use `launch_waveform_annotations.sh` from a **fresh pinned checkout** to prepare
one new build plus 23 waveform jobs, reusing completed calibrated event files.
This covers RF runs 298, 300, **302**, 304, 306, 310, 329, 333, 335, 337, 339,
341, 343 and 345, and other-setting runs 347, 349, 351, 353, 355, 357, 359,
361 and 363. Shared baseline run298 and shared run355 are each processed once.
No conversion, pedestal processing, calibration or summary node is included.
This is waveform processing, not the separate histogram-only combined display.

From normal host tcsh, after creating the fresh checkout and initializing its
pinned decoder submodule, invoke Bash explicitly (an error exits the child
process, not the interactive tcsh session):

```tcsh
/bin/bash "$BASE/source/examples/yall/ari-rf-batch/launch_waveform_annotations.sh" "$BASE"
```

The launcher uses the existing host `yall-run` (at least 0.12.0a7), records its
version and the source/submodule commits, and uses `$EIC_SHELL` when set.
Otherwise it checks the documented `/star/u/pnord/bin/eic-shell`; a nonexistent
or nonexecutable launcher stops preparation. It does not install or change yall.

The default discovery root is `/gpfs01/star/scratch/pnord`; an existing alternate
root can be supplied through `ARI_ANNOTATION_SEARCH_ROOT`. Discovery is bounded
to five directory levels and 10,000 directories, skips source/build/data/attempt
subtrees and symlink directories, and reads only campaign metadata and file
stats. It does not search ROOT contents on the login host. If campaigns are
elsewhere, supply their exact directories directly:

```tcsh
python3 "$REPO/examples/yall/ari-rf-batch/prepare_waveform_annotations.py" --destination "$DEST" --eic-shell "$EIC_SHELL" --campaign "$RF_CAMPAIGN" --campaign "$OTHER_CAMPAIGN" --campaign "$RUN302_CAMPAIGN"
```

These are **campaign directories containing `campaign.json`**, not workspaces.
Paths must be absolute and use only letters, digits, slash, underscore, dot and
hyphen. The destination must be new, outside the source and input workspaces,
and must not contain `.root` because native output naming replaces that text.

For each run, preparation requires a completed latest calibration attempt, an
unchanged recorded event ROOT file, a matching archived waveform command and
unchanged May run database/active-cell configurations. A histogram-only run302
result is insufficient: its calibrated event input and successful calibration
record must be available. Missing runs produce a full error list; none are
silently skipped. If multiple proven inputs exist (for example, a historical
pilot and a full campaign), the launcher lists campaign paths and run inventories
and asks which completed source campaigns to reuse. It never picks the newest
or assumes a full campaign supersedes a corrected single run.

After preparation, the launcher runs `yall-run validate` and `yall-run plan`.
Review the printed input paths and 24-node plan. Only typing **SUBMIT 23** creates
and submits the new campaign; Enter leaves preparation only. There is no
`--accept-repo-scan-recipe` because this workflow does not repeat calibration.

The build worker compiles and tests the new source, then checks all 23 input
ROOT files read-only for nonempty Setup/Data/Calib trees and required branches.
Every waveform job rechecks source/config/input provenance, uses the unchanged
`-d 1 -E 1 -w -r ... -l ...` command, and refuses existing outputs. Native `-w`
writes the derived `_Hists.root`, not necessarily the nominal `-o` event file.
The wrapper requires that histogram and all three paired report products, since
native export warnings alone do not fail analysis. It never adds `-f`, an event
limit or new cuts. Automatic retries remain disabled.

Products are under `work/products/plots/waveform/Run<RUN>/`, with native
`nTOA_<sample>` subdirectories where applicable. Inspect the worker logs, open
both PDFs fully and review their CSVs. Structural checks and synthetic tests do
not establish BNL execution, detector-data validity or scientific correctness.
No BNL task was run to develop this helper.
