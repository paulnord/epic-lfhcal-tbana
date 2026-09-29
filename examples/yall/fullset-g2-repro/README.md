# FullSet G2 reproduction

This example reproduces Fredi's SPS H2 `FullSetG_2` calibration chain from raw
TB2026 data using Yall and HTCondor.

## Inputs

FullSet G2 uses pedestal run `529` and merges muon runs

```text
530 531 532 533 534 535 536 537
```

as `Muon_FullSetG_2`.

It is the later repeat of the FullSet G muon calibration.  Like G1, it uses:

- the V1 summing-board mapping
- `badChannel_HGCROC_SPSTB2026_FullSetG.txt`
- `ToAOffsets_TBSPS2026_FullSetG.csv`

The published reference calibration is:

```text
calibrations/TB2026/calib_SPS-H2_FullSetG_2.txt
```

## Download the raw files at BNL

From this example directory:

```tcsh
tcsh download_raw.tcsh
```

The script downloads runs 529 through 537 to `$LFHCAL_DATA` when that
environment variable is set.  If it is not set, Paul's standard TB2026 PWG
directory is used.  An explicit destination can also be supplied:

```tcsh
tcsh download_raw.tcsh /path/to/raw-data
```

Existing nonempty raw files are left alone.  A download is first written to a
`.part` file and renamed only after `xrdcp` succeeds.

## Run at BNL

Use the bootstrapped LFHCal workspace checkout:

```tcsh
cd "$LFHCAL_REPO/examples/yall/fullset-g2-repro"
source env.tcsh

yall-run validate
yall-run plan

set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

The run table is declared once:

```text
@table runs type run:
    pedestal 529
    muon     530
    muon     531
    muon     532
    muon     533
    muon     534
    muon     535
    muon     536
    muon     537
```

The partial-binding pedestal rule inherits `run=529` from the compatible
conversion row, while `merge-muon` fans in only the eight muon conversion
tasks.

Results are written under:

```text
$LFHCAL_WORK/fullset-g2-repro/
```

with final products:

```text
$LFHCAL_WORK/fullset-g2-repro/final/calib_Final_Muon_FullSetG_2.root
$LFHCAL_WORK/fullset-g2-repro/final/calib_Final_Muon_FullSetG_2_calib.txt
```
