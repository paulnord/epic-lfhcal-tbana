# FullSet G1 reproduction

This example reproduces Fredi's SPS H2 `FullSetG_1` calibration chain from raw
TB2026 data using Yall and HTCondor.

It is a larger validation workflow, not the recommended first Yall/LFHCal test.
For a fresh BNL setup, complete the checks in [`../SETUP.md`](../SETUP.md)
first.

## Inputs

The workflow uses pedestal run `485` and merges muon runs
`484`, `486`, `487`, `488`, `489`, `490`, and `491` as
`Muon_FullSetG_1`.

Set G uses the V1 summing-board mapping, the FullSetG bad-channel map, and the
published FullSetG ToA offsets.

The raw inputs must be readable as:

```text
$LFHCAL_DATA/Run484.h2g
$LFHCAL_DATA/Run485.h2g
$LFHCAL_DATA/Run486.h2g
$LFHCAL_DATA/Run487.h2g
$LFHCAL_DATA/Run488.h2g
$LFHCAL_DATA/Run489.h2g
$LFHCAL_DATA/Run490.h2g
$LFHCAL_DATA/Run491.h2g
```

The published reference calibration is:

```text
calibrations/TB2026/calib_SPS-H2_FullSetG_1.txt
```

## Run table and dependencies

The Yallfile declares the eight runs once in a typed
`@table runs type run:` table. One `convert-{type}-{run}` family converts every
row. `merge-muon` binds `type=muon`, restricting both its patterned parent
fan-in and `@input.parts` to runs `484` and `486`–`491`; pedestal run `485`
cannot leak into the merge.

The `{type}-{run}` pedestal family uses `@each type pedestal`. That explicitly
binds only `type`; the compatible `convert-{type}-{run}` parent supplies the
remaining `run=485`, producing `pedestal-485`. `transfer-g1` depends on the
patterned pedestal family, so changing the pedestal row makes the conversion,
pedestal task, and transfer dependency follow it automatically.

This partial-binding syntax requires yall-run PR #33, merged as commit
`1081e9dd39418262588248272618130ce0503b8a`.

## Run at BNL

Use the normal BNL `tcsh` login/submit session:

```tcsh
cd "$LFHCAL_REPO/examples/yall/fullset-g1-repro"
source env.tcsh

yall-run validate
yall-run plan

set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

Repeat `yall-run status "$C"` to inspect progress.

Results are written under:

```text
$LFHCAL_WORK/fullset-g1-repro/
```

The final products are:

```text
$LFHCAL_WORK/fullset-g1-repro/final/calib_Final_Muon_FullSetG_1.root
$LFHCAL_WORK/fullset-g1-repro/final/calib_Final_Muon_FullSetG_1_calib.txt
```


## Compare with Fredi and build PDF reports

After the campaign has completed, run:

```tcsh
cd "$LFHCAL_REPO/examples/yall/fullset-g1-repro"
source env.tcsh
python3 compare_and_report.py
```

The script compares the reproduced calibration tables with
`calibrations/TB2026/calib_SPS-H2_FullSetG_1.txt`, reports channel-by-channel
and refinement-stage differences, and writes CSV/JSON/text results under:

```text
$LFHCAL_WORK/fullset-g1-repro/report/comparison/
```

It also uses `pdfunite` to assemble the existing ROOT-generated plot PDFs.
The MIP reports follow the same ordering as Fredi's combined calibration summary:
FWHM, Gaussian width, Landau MPV/width, maximum, fit chi-square, per-layer MIP
fits, trigger maps/SNR/suppression, and per-layer trigger primitives.

Outputs are written under:

```text
$LFHCAL_WORK/fullset-g1-repro/report/pdf/
```

including reports for the initial fit and each refinement stage, a
`SummaryMipCalibration_Final_FullSetG_1.pdf` alias for Imp5R, simple pedestal
and transfer plot books, and an all-in-one `CalibrationPlotBook_FullSetG_1.pdf`.
