# Parameter scan set 2

This example runs the second TB2026 HGCROC parameter-scan calibration and
waveform analysis through Yall and HTCondor.

For a fresh BNL installation, follow [`../SETUP.md`](../SETUP.md) first and run
`scan-set-1` before using this larger scan.

## Run pairs

Pedestal / muon pairs:

```text
328 / 329
330 / 331
332 / 333
334 / 335
336 / 337
338 / 339
340 / 341
342 / 343
344 / 345
346 / 347
348 / 349
350 / 351
352 / 353
354 / 355
356 / 357
358 / 359
360 / 361
```

The workflow uses `ToAOffsets_TBSPS2026_ParamScan_2.csv`, the center-2x4 bad
channel map, and `activeCellsHGCROCParameterScan.txt` for the waveform study.

## Run at BNL

Use the normal BNL `tcsh` login/submit session:

```tcsh
cd "$LFHCAL_REPO/examples/yall/scan-set-2"
source env.tcsh
foreach r (328 329 330 331 332 333 334 335 336 337 338 339 340 341 342 343 344 345 346 347 348 349 350 351 352 353 354 355 356 357 358 359 360 361)
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
$LFHCAL_WORK/scan-set-2/
```

Each pair proceeds through conversion, pedestal extraction, transfer of pedestal
and channel corrections, MIP calibration, MIP-trigger selection, three
refinement passes, calibrated-event production, and the HGCROC waveform study.

Useful final areas are:

```text
$LFHCAL_WORK/scan-set-2/refine3/
$LFHCAL_WORK/scan-set-2/calibrated/
$LFHCAL_WORK/scan-set-2/waveform/
$LFHCAL_WORK/scan-set-2/plots/
```

Campaign records and scheduler logs are kept under `$LFHCAL_WORK/campaigns`
when the commands above are used.
