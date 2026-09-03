# Yawl examples

These examples show how to run existing LFHCal executables with `yawl-run` without adding provenance code to the C++ applications.

For the TB2026 HGCROC parameter study, production analysis is split by scan set:

- `scan-set-1/Yawlfile`: runs 296-310, using `ToAOffsets_TBSPS2026_ParamScan_1.csv`.
- `scan-set-2/Yawlfile`: runs 328-361, using `ToAOffsets_TBSPS2026_ParamScan_2.csv`.

Each Yawlfile contains its own explicit pedestal/muon pairs. Cross-scan waveform comparisons are intentionally separate downstream work.

## BNL data root

Define one site-specific environment variable:

```tcsh
setenv LFHCAL_DATA /gpfs01/star/pwg/pnord/eic/2026TBdata
```

The selected raw files are read directly as:

```text
{LFHCAL_DATA}/Run<run>.h2g
```

and Yawl products are written under:

```text
{LFHCAL_DATA}/yawl/scan-set-1/
{LFHCAL_DATA}/yawl/scan-set-2/
```

No shell `CONFIG` variable is required. `TB2026_CONFIG`, `BUILD`, `WORK`, and the scan-set ToA file are internal Yawl `@set` values defined in each Yawlfile.

## Inspect and run

Build LFHCal in `NewStructure/build`, enter one scan-set directory, then:

```tcsh
yawl-run validate
yawl-run plan
```

For campaign records on GPFS:

```tcsh
mkdir -p $LFHCAL_DATA/yawl/campaigns
yawl-run create --campaigns-dir $LFHCAL_DATA/yawl/campaigns
```

Start the exact campaign directory printed by `create`.

The Condor campaigns use `../../../tools/run-in-eic-container.sh` as their `%wrapper`. No LFHCal-specific provenance is embedded into ROOT files; Yawl keeps campaign, task, executable, input/output, scheduler, and attempt provenance in its JSON records.
