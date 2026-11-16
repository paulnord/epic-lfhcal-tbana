Adam requested layer-trend plots, preliminary 2026-11-16
=====================================================
Scope: 23 archived run measurement CSVs, no waveform re-extraction.
Original inputs untouched; copied inputs and SHA256 provenance are alongside this file.
Source: NewStructure/AriLayerTrends.cc (native C++/ROOT).
Output: plots-final/Adam_Layer_Trends_PRELIMINARY.pdf (12 pages), ROOT canvases,
PNGs, linear_fits.csv, layer_measurements.csv, equivalent_shifts.csv.

Reproduce from repository root:
  c++ -O2 $(root-config --cflags) NewStructure/AriLayerTrends.cc $(root-config --libs) -o local-results/adam-20261116/AriLayerTrends
  local-results/adam-20261116/AriLayerTrends --self-test
  local-results/adam-20261116/AriLayerTrends local-results/adam-20261116/measurements.csv configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv NEW_OUTPUT_DIRECTORY
Existing output directories are refused. CMake target AriLayerTrends added; standalone build tested.

METHOD
Cell layer = cell & 63. Eight readout positions per encoded layer.
All successfully extracted positive widths included, including suspicious 2ns widths.
Missing widths are omitted from medians, but included in counts via source CSV flags.
Run-layer median and interpolated IQR summarize channel spread, NOT statistical errors.
Unweighted ordinary least squares fits run medians. Slope SE is residual-based OLS
SE, not calibrated measurement uncertainty. Widths are quantized in 1ns bins.
RF reference fits omit RF1/run300 for diagnostic comparison; full-range sensitivity
retains it. This is not an established physical cut. All individual channel points
are shown, including outliers. No uncertainty-weighted inference is justified.

RF conversion 80/code kOhm is provisional and needs the ASIC revision verified.
CF/CC/CFComp are register codes, not physical capacitance. Nominal run298:
RF9 CF7 CC5 CFComp1; CFComp scan fixed CF5, not CF7. CF5 runs355 and363
are distinct acquisitions, shown separately. RF7/run331 absent, not interpolated.

EQUIVALENT SHIFTS
Delta setting(L) = [nominal median width(L0)-nominal median width(L)] / slope(L).
These are descriptive local, nominal-anchored equivalents, NOT trace resistance
measurements or exact inversions of fitted curves. RF L1 +4.80kOhm and L3
+16.35kOhm toward L0 under provisional conversion. Extrapolated/nonphysical
results explicitly flagged. CF shifts suppressed where |slope|<=2 residual SE,
a numerical safeguard rather than a significance claim. All CF slopes fail it.
CF repeated-setting scatter means added capacitance is not established.

L0-L3 encode 5-layer sums, L4-L7 10-layer sums; physical depths and hardware
conditions differ. Nominal panel is observational, not a controlled comparison.
No reconstructed waveform shapes were generated from scalar measurements.

PENDING
Restore/reanalyse RF7/run331 (pedestal330) and rerun.
RF1/run300 and CC1/run353 need actual waveform TH2s to distinguish mean profile
pathology, crossing failures, or genuine narrow structure; local scalar summaries
cannot resolve that. True 5-vs10 waveform-shape comparison needs source histograms.
RF/CF physical conversions need authoritative confirmation before physical claims.

VALIDATION
Native --self-test: OLS/degenerate x, quantiles, quoted CSV parsing passed.
All40 stored OLS intercepts/slopes independently reproduced with Python stdlib
statistics.linear_regression. Native ROOT generated full PDF and canvas files.
Visual QA of figures completed; originals and existing worktrees left unchanged.

## BNL / tcsh quick start

From a fresh checkout of branch `codex/ari-adam-layer-trends`, enable the site's
ROOT environment (C++17 or newer) and run from the repository root:

```tcsh
./scripts/build_ari_layer_trends.csh
./local-build/AriLayerTrends --make-manifest /path/to/clean/waveform/archive measurements.csv
./local-build/AriLayerTrends measurements.csv configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv plots-adam
```

The archive discovery recursively finds `WaveformGrid_Run*_Measurements.csv`,
uses absolute paths, and refuses duplicate runs or overwriting an existing manifest.
Use a clean archive root, not a directory containing multiple copies of each run.
All default23 runs must be present. Raw ROOT files alone are not measurements;
run the waveform extraction first if a Measurements.csv is missing. No input data
or generated figures are included in Git. Input and output locations are yours.

Run331 is automatically included in the RF scan when present in the manifest;
its recorded settings must be RF7 CF7 CC5 CFComp1. Captions update automatically.
To explicitly choose other run membership, append a fourth positional argument
`scan_runs.csv`, with header `scan,run` and one row per acquisition, using scan
names RF, CF, CC, CFComp. Supply all four scans with at least three acquisitions
each. Fixed settings are validated. Run298 is still required for nominal anchoring.
Explicit scan manifests replace, rather than extend, default scan membership.
The RF1 diagnostic omission is based on register code, not run number.

The tcsh build script follows ROOT's configured compiler flags, including its C++
standard; it does not change your shell or require a full analysis-project build.
BNL itself has not yet been tested. The script and standalone build were tested
on the Mac. Optional developer regression test (not needed for plotting):

```tcsh
python3 NewStructure/Tests/test_ari_layer_trends.py local-build/AriLayerTrends measurements.csv configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv
```

This uses temporary synthetic run331 data ONLY to test inclusion, never as an
actual scientific result. It also checks duplicate discovery and overwrite refusal.
