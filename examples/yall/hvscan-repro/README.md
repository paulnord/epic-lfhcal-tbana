# HV-scan calibration reproduction

This workflow reproduces all nine published TB2026 HGCROC HV-scan muon
calibrations using the shared pedestal run 188.

| Muon run | Bias | Published reference |
| ---: | ---: | --- |
| 201 | 42 V | `calib_SPS-H2_HVScan_42V.txt` |
| 202 | 42.5 V | `calib_SPS-H2_HVScan_42_5V.txt` |
| 195 | 43 V | `calib_SPS-H2_HVScan_43V.txt` |
| 196 | 43.5 V | `calib_SPS-H2_HVScan_43_5V.txt` |
| 194 | 44 V | `calib_SPS-H2_HVScan_44V.txt` |
| 197 | 44.5 V | `calib_SPS-H2_HVScan_44_5V.txt` |
| 198 | 45 V | `calib_SPS-H2_HVScan_45V.txt` |
| 199 | 45.5 V | `calib_SPS-H2_HVScan_45_5V.txt` |
| 200 | 46 V | `calib_SPS-H2_HVScan_46V.txt` |

The recipe follows Fredi's HVScan configuration: V2 summing-board mapping,
`badChannel_HGCROC_SPSTB2026_OnlyCenter4x6.txt`, and
`ToAOffsets_TBSPS2026_HVScan.csv`.

Download the ten raw inputs:

```tcsh
tcsh download_raw.tcsh
```

Then run from the bootstrapped workspace:

```tcsh
source env.tcsh
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C"
```

The single typed run table contains pedestal 188 and muons 194-202. The
pedestal is converted and fitted once; each muon then fans out through transfer,
initial MIP calibration, skim, five refinements, and a final calibration under
`$LFHCAL_WORK/hvscan-repro/final/`.
