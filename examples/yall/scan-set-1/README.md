# Parameter scan set 1

This example runs the first TB2026 HGCROC parameter-scan calibration and waveform
analysis through Yall and HTCondor.

For a fresh BNL installation, follow [`../SETUP.md`](../SETUP.md) first. This is
the recommended first production LFHCal workflow after the smoke tests.

## Run pairs

Pedestal / muon pairs:

```text
296 / 298
299 / 300
303 / 304
307 / 308
309 / 310
```

The workflow uses `ToAOffsets_TBSPS2026_ParamScan_1.csv`, the center-2x4 bad
channel map, and `activeCellsHGCROCParameterScan.txt` for the waveform study.

## Run at BNL

Use the normal BNL `tcsh` login/submit session:

```tcsh
cd "$LFHCAL_REPO/examples/yall/scan-set-1"
source env.tcsh
foreach r (296 298 299 300 303 304 307 308 309 310)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

Repeat `yall-run status "$C"` to inspect progress. Use a fresh `LFHCAL_WORK` for
a clean rerun rather than targeting an existing output tree.

## Outputs

Results are written under:

```text
$LFHCAL_WORK/scan-set-1/
```

Each pair proceeds through conversion, pedestal extraction, transfer of pedestal
and channel corrections, MIP calibration, MIP-trigger selection, three
refinement passes, calibrated-event production, and the HGCROC waveform study.

Useful final areas are:

```text
$LFHCAL_WORK/scan-set-1/refine3/
$LFHCAL_WORK/scan-set-1/calibrated/
$LFHCAL_WORK/scan-set-1/waveform/
$LFHCAL_WORK/scan-set-1/plots/
```

Campaign records and scheduler logs are kept under `$LFHCAL_WORK/campaigns`
when the commands above are used.
