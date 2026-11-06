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

The paired PDFs use matching channel order and pagination, with absolute and
normalized views and up to 64 channels per page. Existing `Waveform_*` products
remain unchanged. Compare each original page with its annotated counterpart.
Fixed-TOA selections use the existing `nTOA_<sample>` subdirectory. Absolute
scaling, like the saved 64-cell producer, excludes samples after the bin
containing 200 ns so late noise does not flatten the pulses; late values can
therefore extend outside the displayed y range.
For a valid measurement, annotations contain exactly three vertical guides
(left width endpoint, peak time, right width endpoint) and one horizontal
peak-amplitude guide. Invalid widths omit the width guides, rather than
inventing a zero width; measurement/status values remain available in the CSV.

This is a display/export addition: **zero new fits, cuts, waveform extractions,
or changes to timing or baseline conventions**. It reuses Ari's peak-bin timing
and bin-center width endpoints, including existing invalid-measurement flags.
Check the worker test log, paired PDFs and CSV before extending the pilot.
An annotation/export failure is logged as a warning so the normal histogram
output is still saved. Check that all three new files exist and that both PDFs
open fully; overall analysis success alone does not establish report completion.
No BNL build, analysis run or submission was executed for this handoff.
