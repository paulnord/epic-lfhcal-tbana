# Native ROOT RF resistance and channel diagnostics

This extends the existing `plot_all_scans.py` / `prepare_all_scans.py` plot-only
workflow. It does **not** run event conversion, waveform extraction, or fitting.
The original all-scans canvases/graphs, box convention and output filenames are
unchanged for the same 22 inputs. `--rf-diagnostics` adds native PyROOT objects,
PDF pages and PNGs; no Matplotlib dependency is used.

## Existing run 302 (RF code 2)

The May database records signal run302 / pedestal301 at RF2, CF7, CC5, CFComp1.
Ari's original selected list omitted it; no quality-rejection reason is known.
The plot-only workflow now includes it automatically if this file exists:

`RF_WORKSPACE/products/waveform/calibratedHGCROC_wave_Run_302_Hists.root`

Otherwise provide `--run302-input /absolute/path/to/the/existing/Run302_Hists.root`.
The basename need not match; the supplied path is explicitly assigned to run302.
You must identify the correct completed run302 output, not another run's file.
The original saved measurement histograms and status guards are required. A file
without those histograms fails clearly; nothing is silently re-extracted.
No values are invented if run302 is absent. The preparation manifest freezes the
22/23-file inventory: a file appearing later is not silently added to a job.
Run302 data were not supplied with the original 22-run uploaded result, so the
actual-data local demonstration has 13 RF settings, not 14.

## BNL (tcsh; one plot-only job)

Use a **new checkout containing this change**, not the source tree of a running
campaign. Until the change is published, apply the supplied patch to the stated
base commit in that new checkout. `REPO` is that checkout; `RF` and `OTHER` are the
completed waveform workspaces (the directories containing `products/waveform`).
Neither preparation nor validation submits anything.

```tcsh
set DEST = /gpfs01/star/scratch/pnord/ari-root-diagnostics-`date -u +%Y%m%dT%H%M%SZ`
python3 "$REPO/examples/yall/ari-rf-batch/prepare_all_scans.py" --rf-workspace "$RF" --other-workspace "$OTHER" --destination "$DEST" --eic-shell /star/u/pnord/bin/eic-shell --rf-diagnostics
cd "$DEST" && yall-run validate && yall-run plan
```

If run302 is elsewhere, append `--run302-input "$R302"` to the preparation
command after setting `R302` to the actual completed histogram file path.
Expect one plot-only task, 22 or23 waveform inputs, and six driver/configuration/
provenance inputs. Inspect `preparation.json`: run302 must appear there if included.
Only after successful validation, and when ready to submit explicitly:

```tcsh
set C = `yall-run create --campaigns-dir "$DEST/campaigns"`
echo "$C"
yall-run status "$C"
```

Stop if creation failed. To submit the successfully created campaign:

```tcsh
yall-run start "$C"
yall-run status "$C"
```

Outputs are under `$DEST/results` (or the runner's recorded output destination).
The EIC worker supplies production ROOT; the local QA wheel is not installed or
required on BNL. Source/configuration SHA256 and input size/mtime are checked
before plotting, so do not edit this checkout or the inputs after preparation.

## Re-render an already exported combined measurement CSV

This is the same driver, not a parallel plotting implementation. It validates
one row per selected cell, settings, statuses, missing values and finite values.
It requires the complete 22-run inventory, optionally plus run302. It cannot add
run302 to an old CSV that lacks those measurements.

```sh
python3 examples/yall/ari-rf-batch/plot_all_scans.py \
  --measurements-csv /absolute/path/to/measurements.csv \
  --rundb configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv \
  --rf-diagnostics --output /absolute/path/to/a/new/output
```

## Scientific conventions and saved outputs

- `HGCROC_RFResistance.*`: true numeric resistance spacing, arithmetic means AND
  medians for amplitude/FWHM/peak time, finite sample counts, and full-range
  individual-channel values. The large80kOhm anomalies stay visible. Summary
  JSON and native ROOT graphs support independent numeric checks.
- `HGCROC_RFChannels.*`: nominal configuration-derived maps, extraction-failure
  distinctions, and matched-cell scatter/correlation comparisons. ROOT objects
  retain the plotted data; numeric metadata records finite-pair counts. Missing
  widths are not zero. Narrow finite widths remain present, not cut away.
- Existing `HGCROC_AllScans{,Main}.{root,pdf,png}` conventions are preserved (there
  is one `HGCROC_AllScans.root` containing both original canvases). Existing CSV
  and input metadata remain available; `rf_diagnostics_provenance.json` records
  additional code/config/CSV hashes, ROOT version and run302 inclusion.
- Every statistic is across the selected channels' **mean-waveform metrics**,
  not a distribution of individual events or uncertainty on a mean. Per-metric
  finite populations can differ. Correlations are descriptive, not evidence of
  coupling or a causal diagnosis. Statistical outliers are not exclusions.
- **Provisional H2GCROC3B mapping: R[kOhm]=80/RFcode.** Installed ASIC revision is
  not verified. Code2 would be40kOhm under this mapping. Source implementation:
  https://gitlab.cern.ch/sjia/h2gcalibx/-/blob/c559c954110ad64b949f0d03ff7f5d68d22894c0/config/h2gcroc_1v4_r2.json
  and repository `NewStructure/CommonHelperFunctions.h`. This is not a claim
  that the installed May hardware was independently identified.
- Geometry uses only the recorded nominal May configuration with SHA256
  `0d94c85012210baeec241b5fea4af7e74b28362450597b1948a82a176319477e`.
  The selected cells span nominal module2/ASIC1 and module3/ASIC5. The map does
  not establish board serials, actual wiring, or an independently read embedded
  Setup object. A different mapping file is rejected rather than guessed.

## Checks

```sh
python3 -m unittest discover -s examples/yall/ari-rf-batch -p test_plot_all_scans.py -v
python3 -m unittest discover -s examples/yall/ari-rf-batch -p 'test_root_rf_*.py' -v
python3 -m unittest discover -s examples/yall/ari-rf-batch -p test_rf_diagnostics_pipeline.py -v
```

PyROOT enables native object read-back tests; without it they explicitly skip.
The final command requires `yall-run` for actual preparation-graph tests. It
otherwise skips those cases, not the inventory/CSV validation tests. Synthetic
run302 tests exercise inclusion only; they are not presented as real run302 data.
