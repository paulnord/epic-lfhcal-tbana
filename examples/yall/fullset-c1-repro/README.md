# FullSetC_1 reproduction

This example reproduces Fredi's SPS H2 `FullSetC_1` merged-muon calibration
chain from raw TB2026 data using Yall and HTCondor.

Pedestal: `137`

Muon runs, in Fredi's merge order:

```text
147 148 149 146 145 144 141 142 143 140 139 138
```

The merged input is `Muon_FullSetC_1`. This set uses the V2 summing-board
mapping, the shared FullSetA-F bad-channel map, and
`configs/TB2026/ToAOffsets_TBSPS2026_FullSetC.csv`.

Published reference:

```text
calibrations/TB2026/calib_SPS-H2_FullSetC_1.txt
```

## Download raw files

```tcsh
tcsh download_raw.tcsh
```

The helper uses `$LFHCAL_DATA` when set, otherwise Paul's standard TB2026 PWG
directory. Existing nonempty files are skipped and new downloads go through a
temporary `.part` file.

## Run at BNL

```tcsh
cd "$LFHCAL_REPO/examples/yall/fullset-c1-repro"
source env.tcsh
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C"
```

Results go under `$LFHCAL_WORK/fullset-c1-repro/`. The final text
calibration is
`final/calib_Final_Muon_FullSetC_1_calib.txt`.

The run table is the single source of truth. The pedestal rule binds only
`type=pedestal` and inherits the compatible run number, requiring yall-run PR
#33 (`1081e9dd39418262588248272618130ce0503b8a`).

## Compare with the published calibration

```tcsh
python3 ../compare_fullset.py --set-name FullSetC_1
```

The common tool compares refinement stages and builds combined PDF plot books,
using `pdfunite`, `qpdf`, or Ghostscript.
