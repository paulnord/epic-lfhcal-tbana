# Yawl examples

These examples show how to run existing LFHCal executables with `yawl-run` without adding provenance code to the C++ applications.

## Where to start

The examples are intentionally arranged from small teaching examples to full production workflows:

- `hgcroc-study/`: one task. The smallest LFHCal example.
- `calibration-pair/`: two dependent tasks.
- `lfhcal-simple/`: the recommended introductory workflow. It converts a list of raw runs, creates calibrations from a list of pedestal/MIP pairs, and creates summaries from another list of runs.
- `hgcroc-study-condor/`: a small example using the Condor backend.
- `scan-set-1/` and `scan-set-2/`: advanced production examples with a larger DAG and finer-grained dependencies.

Start with `lfhcal-simple` if you want to see Yawl fan-out over ordinary lists and correlated pairs without the full TB2026 production machinery.

## TB2026 production workflows

For the TB2026 HGCROC parameter study, production analysis is split by scan set:

- `scan-set-1/Yawlfile`: runs 296-310, using `ToAOffsets_TBSPS2026_ParamScan_1.csv`.
- `scan-set-2/Yawlfile`: runs 328-361, using `ToAOffsets_TBSPS2026_ParamScan_2.csv`.

Each production Yawlfile contains its own explicit pedestal/MIP pairs. Cross-scan waveform comparisons are intentionally separate downstream work.

These scan-set examples are useful demonstrations of a real analysis, but they are not intended to be the first introduction to Yawl syntax.

## BNL data root

The examples that read TB2026 raw data use one site-specific environment variable:

```tcsh
setenv LFHCAL_DATA /gpfs01/star/pwg/pnord/eic/2026TBdata
```

Raw files are then referenced as:

```text
{LFHCAL_DATA}/Run<run>.h2g
```

The production scan-set workflows write products under:

```text
{LFHCAL_DATA}/yawl/scan-set-1/
{LFHCAL_DATA}/yawl/scan-set-2/
```

No shell `CONFIG` variable is required. Configuration paths and build paths are Yawl `@set` values inside each Yawlfile.

## Inspect and run

Build LFHCal in `NewStructure/build`, enter an example directory, then:

```tcsh
yawl-run validate
yawl-run plan
```

To create a frozen campaign:

```tcsh
yawl-run create
```

For production campaign records on GPFS:

```tcsh
mkdir -p $LFHCAL_DATA/yawl/campaigns
yawl-run create --campaigns-dir $LFHCAL_DATA/yawl/campaigns
```

Start the exact campaign directory printed by `create`.

The Condor examples use `tools/run-in-eic-container.sh` as their `%wrapper`. No LFHCal-specific provenance is embedded into ROOT files; Yawl keeps campaign, task, executable, input/output, scheduler, and attempt provenance in its campaign records.
