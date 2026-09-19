# FullSetD_2 reproduction

This example reproduces Fredi's SPS H2 `FullSetD_2` merged-muon calibration
chain from raw TB2026 data using Yall and HTCondor.

Pedestal: `264`

Muon runs, in Fredi's merge order:

```text
266 267 268 269 270
```

The merged input is `Muon_FullSetD_2`. This set uses the V2 summing-board
mapping, the shared FullSetA-F bad-channel map, and
`configs/TB2026/ToAOffsets_TBSPS2026_FullSetD.csv`.

Published reference:

```text
calibrations/TB2026/calib_SPS-H2_FullSetD_2.txt
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
cd "$LFHCAL_REPO/examples/yall/fullset-d2-repro"
source env.tcsh
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C"
```

Results go under `$LFHCAL_WORK/fullset-d2-repro/`. The final text
calibration is
`final/calib_Final_Muon_FullSetD_2_calib.txt`.

The run table is the single source of truth. The pedestal rule binds only
`type=pedestal` and inherits the compatible run number, requiring yall-run PR
#33 (`1081e9dd39418262588248272618130ce0503b8a`).

## Compare with the published calibration

```tcsh
python3 ../compare_fullset.py --set-name FullSetD_2
```

The common tool compares refinement stages and builds combined PDF plot books,
using `pdfunite`, `qpdf`, or Ghostscript.
