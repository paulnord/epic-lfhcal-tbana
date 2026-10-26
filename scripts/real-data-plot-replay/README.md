# E2 real-data fit-rendering replay

Reproduce **cell1344, legacy E2/refine5**, using all entries of the original
refine5 input and the original saved fit. No fitting, production edits, or plot
restyling. This is an isolated reproduction helper, not a change to the analysis.

## Run at BNL

Activate one consistent ROOT/PyROOT/compiler environment first. Historical ROOT
was **6.40.04**; local validation used **6.40.00**. Python3 must be able to import
the same ROOT version reported by `root-config`. Public GitHub access is needed
for two SHA-verified source headers. No additional Python packages are needed.

From an existing checkout (your current branch/files are not switched):

```bash
git fetch https://github.com/paulnord/epic-lfhcal-tbana.git repro-real-data-e2-cell1344-20261026
git worktree add --detach ../lfhcal-real-data-replay FETCH_HEAD
cd ../lfhcal-real-data-replay
bash scripts/real-data-plot-replay/run.sh \
  /gpfs/mnt/gpfs01/star/scratch/pnord/lfhcal/adaptive-fullchains-remaining-20260929T014858Z \
  "$HOME/lfhcal-real-fit-$(date -u +%Y%m%dT%H%M%SZ)"
```

The worktree and output paths must not already exist. No `git pull`, branch
checkout, force operation, or modification of the original campaign is needed.
The output is a fresh directory outside that campaign. Inputs are read-only.
The script records input SHA256 (one additional sequential read), compiles the
archived classes locally, scans every input event, and writes separate legacy
and faithful PDF/PNG plots plus `checks.json`, reconstructed histograms, and logs.
Compilation/event processing logs are in that output directory.

Required original inputs relative to the campaign directory:

```
manifest.json
source-hashes.json
sources/legacy/NewStructure/*.h, *.cc
sources/legacy/configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv
legacy/e2/select/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_FullSetE_2.root
legacy/e2/refine4/rawHGCROC_wPedwMuon_wBC_Imp4R_Muon_FullSetE_2_calib.txt
legacy/e2/refine5/rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_FullSetE_2.root
legacy/e2/refine5/rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_FullSetE_2_Hists.root
```

These are recorded historical paths, not a claim that they remain available at
BNL. Missing or changed inputs cause an error. Recover the original file rather
than substituting another campaign or rerunning a fit. The final full-precision
ROOT calibration cannot be replaced with rounded calibration text.

## What is held fixed

- Historical `Setup`, `Calib`, `Event`, `Hgcroc`, `TileSpectra`, model callback and
  common plot helpers: source files verified against the archived source manifest.
- Input Calib is read first, then original refine4 text is applied through the
  production parser. The original segmented average and integration count1 are
  used. Trigger decision is the stored primitive strictly between 0.8 and 2.5
  times that average; no trigger-bit reuse or neighbor recomputation.
- ADC is the already-integrated stored ADC; no second pedestal subtraction.
- Original 15% error expression, including NaNs in empty bins, is preserved.
- Original saved parameters, errors, limits, range, Npx, chi-square and NDF are
  restored into a live historical callback, never a deserialized interpolation.
- The actual existing single-tile production function and caller settings are
  used: same inclusive/triggered data, styles, overlays, legend, canvas and
  -100..250 ADC extent. Only reviewed fit drawing differs. No zoom/annotations.

Before plotting, reconstructed triggered edges, counts, errors, Sumw2 and entries
must exactly match the original histogram, including flow bins and NaNs. The
original histogram and fit must themselves match an independently archived full
record fingerprint. Final raw scale/width/noise/BC metadata are gated too.
Fit and histogram metadata are checked again after drawing; all four output
files must have valid PDF/PNG signatures before reporting success.

**Inclusive has no independently archived checksum.** It is regenerated from
the original unchanged selected-event file. Trigger equality cannot establish
that rejected events were unchanged; the input SHA256 recorded now is an audit
record, not comparison against an unavailable historical checksum. “Inclusive”
means all target-cell observations in the original refine5 input, not raw-event
reprocessing. The original stage generated layer pages; this uses its existing
single-tile production presentation, not a byte-identical old saved image.

## Pins and measured reference

- Historical base: `924ad82de6d150534b4d7684b5638df92c0a2016`.
  Actual source identity is the archived per-file hashes, not this base alone.
- Reviewed renderer: `51a43cb548edeb6a418be037a402ae1e21387c23`
  ([PR91](https://github.com/eic/epic-lfhcal-tbana/pull/91)).
  Only `NewStructure/PlotHelper.h` and `FitCurveDrawing.h` are fetched.
- Measured reference: `fit-range-study-inputs-20261001-v2`, retained on
  2026-10-01; source Hists keys
  `IndividualCellsTrigg/hspectramipTriggADCCellID1344` and
  `IndividualCellsTrigg/fmipmipTriggHGCellID1344`; **18,030 entries**.
- Independently retained histogram+fit canonical JSON fingerprint:
  `0e34969ed77e0779a46d7df8f334c0f443591b27688ca677aa0d55ad67374ba8`.
- All source/reference/download digest constants and fingerprint serialization
  are visible in `run.py`; extracted function bodies must differ only by the
  reviewed drawing calls/range sentinels and trailing whitespace.

The original fit is pathological (chi-square/NDF about452.6), **not a good
physics fit**. Faithful drawing exposes the same fitted evaluator, including
legacy quadrature structure. It does not improve the model or fit quality.

## Validation status

**Full BNL data run: NOT EXECUTED locally.** No authentic full-data inclusive
figure is claimed by these tests.

Local ROOT6.40.00 checks passed: source/function parity, original-record hash,
Setup/Calib/Event/HGCROC ROOT round-trip, calibration tolerance/segmented average,
strict trigger endpoints, ADC preservation, historical errors/NaNs, intentional
histogram mismatch rejection, live sampling/fit metadata preservation, and actual
production PDF/PNG rendering. The command bootstrap was then exercised end to
end on a deliberately synthetic event fixture: 18,040 events, 18,030 triggered
entries matching the retained histogram, plus ten synthetic rejected events.
This validates mechanics, not the missing authentic inclusive distribution.
Public URLs were verified separately; local bootstrap tests substituted their
exact hash-pinned bytes. Missing-input/wrong-campaign/output-collision tests pass.
Independent source/code review found no critical parity or no-refit defect.

No raw event data, calibration files, generated plots, binaries, build outputs,
private Library links, credentials, or local execution logs are included here.
