# Yawl examples

These examples show how to run existing LFHCal executables with `yawl-run` without adding provenance code to the C++ applications.

For the TB2026 HGCROC parameter study, the production analysis is split by scan set:

- `scan-set-1/Yawlfile`: runs 296-310, using `ToAOffsets_TBSPS2026_ParamScan_1.csv`.
- `scan-set-2/Yawlfile`: runs 328-361, using `ToAOffsets_TBSPS2026_ParamScan_2.csv`.

Each Yawlfile contains its own explicit pedestal/muon pairs and writes all products to a persistent GPFS work tree. Cross-scan waveform comparisons are intentionally not part of either production campaign; they can be a separate downstream campaign once both scan sets are complete.

On the current BNL setup:

```tcsh
setenv LFHCAL_RAW /work/eic3/EPIC/TestBeam/LFHCAL/CERN/2026/2026_SPSH2/raw
setenv LFHCAL_WORK /gpfs01/star/pwg/pnord/eic/2026TBdata/yawl
```

The two campaigns then write under:

```text
/gpfs01/star/pwg/pnord/eic/2026TBdata/yawl/scan-set-1/
/gpfs01/star/pwg/pnord/eic/2026TBdata/yawl/scan-set-2/
```

with subdirectories for converted, pedestal, transfer, MIP, refinement, calibrated, waveform, and plot products.

Build LFHCal in `NewStructure/build`, then enter the desired scan-set directory and inspect the campaign:

```tcsh
yawl-run validate
yawl-run plan
```

For durable campaign provenance on the same GPFS area:

```tcsh
mkdir -p $LFHCAL_WORK/campaigns
yawl-run create --campaigns-dir $LFHCAL_WORK/campaigns
```

Start the exact campaign directory printed by `create`:

```tcsh
yawl-run start $LFHCAL_WORK/campaigns/<campaign-id>
```

The Condor campaigns use `../../../tools/run-in-eic-container.sh` as their `%wrapper`.

No LFHCal-specific provenance is embedded into ROOT files. Yawl keeps campaign, task, executable, input/output, scheduler, and attempt provenance in its JSON records.
