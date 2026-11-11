# Scan book display replay: prominent identifiers and isolated outliers

`CombineWaveformBooks` defaults to `isolated`. Specify it explicitly for replay.
All 26 pages in both books now have a large scan-code identifier (e.g. `RF=1`),
white type on a filled scan-family banner, run, group, page number, and all four integer settings.
The prior v2 palette is restored: RF #176B79, CC #6550A1, CF #A86520, CFComp #357049. Nominal RF resistance
is secondary. RF ordering and all group memberships remain unchanged.

## Display rule and limits

For each run and cell-ID layer, collect the saved positive peak amplitudes of
present profiles. With at least four peaks, compute linearly interpolated Q1 and
Q3 and flag amplitudes **strictly greater than Q3 + 1.5 (Q3 - Q1)**. The criterion
uses neither run numbers nor cell-specific exceptions. Missing FWHM does not
invalidate a finite saved peak. A missing/no-positive-peak cell does not enter
the peak population. Invalid supplied peak/width measurements fail validation.

Independently apply the same upper Tukey fence to the visible positive maximum
and visible negative magnitude of each profile within the common x window.
Each extent test requires at least four profiles with finite visible samples;
all-nonfinite and missing profiles do not count. Union the three flags and label
the reasons (`high peak`, `visible + excursion`, `visible - excursion`). This
catches ordinary-peak profiles with extreme negative or post-200-ns excursions.
A no-peak profile can be flagged by its visible extent, but is never normalized.

In `isolated` mode, flagged cells are excluded from both ends of the shared
layer axis and get violet frames, `OUTLIER`, `own ADC axis`, and unchanged measured
amplitude labels. Their independent axis includes all finite profile contents
within the common displayed x window, including negative excursions and bins
after 200 ns, plus the saved peak and 12% range padding. No remeasurement, data
cut, interpolation, or fit occurs. Samples outside that displayed time window
remain outside it. Nonfinite profile contents do not define an axis.

Normalized curves remain **profile / saved cell peak**, never profile / display
maximum. Flagged cells retain that normalization but use an explicitly labeled
`own A/peak axis`, widened when required to show the same finite tails. Normal
cells retain [-0.08, 1.12]. Missing positive peaks remain explicitly unplottable
in normalized view. Violet clipping arrows are separate indicators of values
outside the displayed y range, not the statistical flag.

These are **display flags**, not data-quality vetoes or a general shape anomaly
classifier. Unflagged cells retain the existing through-200-ns range convention
and explicit clipping indicators. Fewer than four eligible samples for any one
criterion produce no statistical exclusion by that criterion. A whole anomalous layer/run may not be an
outlier relative to its peers; no scientific rejection should be inferred.

Cell-level isolation is appropriate because axes are already per run and layer,
not shared between pages. Visual inspection of the actual earlier books showed
run 343 cell 1155 (layer 3), run 339 cell 1607 (layer 7), and run 363 cell 1602
(layer 2) near 1100 ADC suppressing their layer neighbors. These observations
motivate the rule but are not hardcoded, and actual flags must be verified from
the replay inputs, not inferred solely from the PDF.

Explicit legacy modes remain available: `layer` (all cells share their layer's
range), `robust` (old upper-only exclusion with clipping), and `global` (full
search-window shared range). They preserve their prior scaling semantics.

## Verification

Build `CombineWaveformBooks`, `test_waveform_books`, `test_waveform_annotations`,
`test_waveform_measurement`, and `test_fit_curve_legend`, then run CTest. Tests
cover strict fence equality, zero IQR, sample count <4, absent profiles,
no-positive-peak cells, missing FWHM with valid peak, nonfinite supplied peaks,
negative-only/no-peak and ordinary-peak post-200-ns extremes, all-nonfinite
profiles, negative and post-200-ns tails on independently scaled cells, unchanged source
profiles and supplied measurements, preserved normalization, and legacy modes.
The book fixture generates all 26 pages twice with a known 10x high-peak cell.
Check both PDFs' page counts and render RF, CC, CF, and CFComp headers plus the
flagged cell and its same-layer neighbor at readable resolution.

## BNL display-only replay (after code transfer is authorized)

Do not reprocess events or recalibrate. Use the existing verified 23-pair
manifest at `/gpfs01/star/scratch/pnord/ari-books-20261111/inputs.csv`,
which references saved ROOT profiles and Measurements CSVs in the original
rebuild and run-302 annotation trees. Verify that manifest before use. A manifest has
`run,profile_root,measurements_csv` and exactly the established 23 runs.
Set `MANIFEST` to that verified manifest and `DATABASE` to the matching checked
run database; do not invent paths or substitute a newly extracted measurement.

```sh
# In a separate checkout of the reviewed local patch, with ROOT configured:
cmake -S NewStructure -B build-display
cmake --build build-display --target CombineWaveformBooks --parallel 1
: "${MANIFEST:?Set to the verified existing 23-run input manifest}"
: "${DATABASE:?Set to the verified matching run database}"
OUTPUT=/gpfs01/star/scratch/pnord/ari-books-isolated-$(date -u +%Y%m%dT%H%M%SZ)
mkdir "$OUTPUT"  # fails if already present; never reuse prior products
build-display/CombineWaveformBooks "$MANIFEST" "$DATABASE" "$OUTPUT/AllScans" isolated
pdfinfo "$OUTPUT/AllScans_Unnormalized.pdf" | grep Pages
pdfinfo "$OUTPUT/AllScans_Normalized.pdf" | grep Pages
# Both must report 26. Inspect pages 2, 4, 14, 22, and 26 and group boundaries.
```

The writer refuses existing output PDF names. Keep the input manifest, source
ROOT/CSV files, original books, and previous output directories unchanged. Local
synthetic verification is not a claim that these actual-data BNL books have been
regenerated or published.

### Preparation helper with exact source revision

The existing preparation helper keeps its historical default revision and
`layer` mode for compatibility. New `isolated` preparation therefore requires
`ARI_SOURCE_COMMIT`, a full lowercase 40-hex revision containing the new mode.
It clones a separate checkout, verifies that exact HEAD, checks mode support,
and records both source revision and scale in `preparation.json`. The generated
worker rechecks tracked source and input provenance before and after replay.

After the local patch is reviewed and publishing is explicitly authorized,
replace `PUBLISHED_FULL_COMMIT` below with the verified remote commit containing
this change. An unpublished local SHA is not yet usable from the remote default
source; this document does not imply publication has happened.

```sh
# Run in bash on the normal BNL shell, not inside an EIC/Condor worker.
export ARI_SOURCE_COMMIT=PUBLISHED_FULL_COMMIT
/bin/bash /path/to/reviewed/prepare_ari_books.sh \
  /gpfs01/star/scratch/pnord/ari-books-isolated-20261111 isolated
# Preparation performs no submission. Review validation/plan/provenance first.
# Then, only when submission is authorized:
/bin/bash /gpfs01/star/scratch/pnord/ari-books-isolated-20261111/submit_books.sh
```

Keep the normal helper defaults for the exact existing input tree and run-302
annotation root; do not point it at the PDF-only products directory. If the
proposed fresh destination already exists, choose a new fresh name. Never
modify the completed `ari-books-20261111` workspace or the ongoing archive.
`test_prepare_ari_books.py` verifies the full revision, isolated mode, independent
checkout, exact 23-pair inventory, unchanged inputs, refusal of reused output,
invalid revisions, missing explicit revision, unsupported source mode, and
legacy layer acceptance. Yall and EIC are offline stubs in that test, not a
claim of actual scheduler submission or execution.

## Direct local EIC run (no queue)

Use a permitted BNL interactive analysis node, not an SSH gateway. BNL's
[interactive-use guidance](https://docs.sdcc.bnl.gov/help/linux-basics/) says
interactive work should be short; work taking more than a few minutes belongs
on approved compute resources. Confirm the node is appropriate before starting.
This helper builds only the plotting target, serially, and reads saved profiles;
it does not process events, submit a job, install software, or write an archive.
If it is unexpectedly long, stop and inspect the log rather than retrying or
starting another copy. Arrange an approved longer interactive allocation if
needed; the helper does not silently switch to a queue.

From the checkout containing this helper, use the complete reviewed/published
40-character commit, not a branch or abbreviated SHA. The `/usr/bin/env`
assignments below work from tcsh as well as Bash:

```sh
/usr/bin/env ARI_SOURCE_COMMIT=FULL_REVIEWED_40_HEX_COMMIT /bin/bash examples/yall/ari-rf-batch/run_ari_books_local.sh /gpfs01/star/scratch/pnord/ari-books-local-FRESH_UNIQUE_NAME isolated
```

Replace both placeholders. The destination must not exist. The default launcher
is the already installed `/star/u/pnord/bin/eic-shell`; `EIC_SHELL` can select
another existing authorized launcher. `ARI_SOURCE_REPO` can select an existing
local repository without modifying it. `ARI_INPUT_ROOT` and `ARI_RUN302_ROOT`
can select verified saved-input trees; defaults match the preparation helper.
No `yall-run`, Condor, or batch-worker environment is needed. The host helper
rejects accidental execution inside a batch worker.

Before building, the helper validates all **23 exact ROOT/CSV pairs**, including
run 302's separate tree, and hashes every input. It clones into the fresh
destination, checks out the full SHA, and verifies source and inputs before and
after the replay. CMake builds only `CombineWaveformBooks` with `--parallel 1`;
ROOT and OpenMP thread limits are also one. The container-side command uses the
same stdin quoting/transport as the existing EIC worker wrapper, without its
scheduler requirement. All build products and logs stay in the new destination.

Success requires both PDFs, unchanged source/inputs, and
`products/BOOKS_READY`. Outputs are `products/AllScans_Unnormalized.pdf` and
`products/AllScans_Normalized.pdf`; `products/SHA256SUMS` records their hashes.
When `pdfinfo` is installed inside EIC, both 26-page counts are also checked.
Otherwise verify counts after transfer before considering the books reviewed.
Inspect `local-run.log`, `preparation.json`, and `environment.txt` for provenance.
A failed run is preserved for diagnosis. Do not reuse its destination or launch a
blind retry. Offline stub tests exercise the helper but do not constitute a BNL
run or real-data validation.
