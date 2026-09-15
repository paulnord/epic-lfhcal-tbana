# Yall examples

These examples show how to run existing LFHCal executables with `yall-run` without adding provenance code to the C++ applications.

These examples target **yall-run 0.8.1**.

## Where to start

The examples are intentionally arranged from small teaching examples to full production workflows:

* `hgcroc-study/`: one task. The smallest LFHCal example.
* `calibration-pair/`: two dependent tasks.
* `lfhcal-simple/`: the recommended introductory workflow. It converts a list of raw runs, creates calibrations from a list of pedestal/MIP pairs, and creates summaries from another list of runs.
* `hgcroc-study-condor/`: a small example using the Condor backend.
* `scan-set-1/` and `scan-set-2/`: advanced production examples with a larger DAG and finer-grained dependencies.

Start with `lfhcal-simple` if you want to see Yall fan-out over ordinary lists and correlated pairs without the full TB2026 production machinery.

## TB2026 production workflows

For the TB2026 HGCROC parameter study, production analysis is split by scan set:

* `scan-set-1/Yallfile`: runs 296-310, using `ToAOffsets_TBSPS2026_ParamScan_1.csv`.
* `scan-set-2/Yallfile`: runs 328-361, using `ToAOffsets_TBSPS2026_ParamScan_2.csv`.

Each production Yallfile contains its own explicit pedestal/MIP pairs. Cross-scan waveform comparisons are intentionally separate downstream work.

These scan-set examples are useful demonstrations of a real analysis, but they are not intended to be the first introduction to Yall syntax.

## Data and work directories

The production examples separate the shared raw-data location from the user's writable analysis area:

```tcsh
setenv LFHCAL_DATA /path/to/TB2026/raw-data
setenv LFHCAL_WORK /path/to/your/yall-work
```

Raw files are then referenced as:

```text
{LFHCAL_DATA}/Run<run>.h2g
```

The production scan-set workflows write products under:

```text
{LFHCAL_WORK}/scan-set-1/
{LFHCAL_WORK}/scan-set-2/
```

Configuration paths and build paths are Yall `@set` values inside each Yallfile.

## Condor container

The Condor examples use `tools/run-in-eic-container.sh`.

Set `EIC_CONTAINER_IMAGE` to the pinned EIC container image that the campaign should use:

```tcsh
setenv EIC_CONTAINER_IMAGE /path/to/pinned/eic-container
```

The wrapper deliberately does not default to a moving `nightly` image. This keeps the execution environment an explicit part of the campaign setup.

## Inspect and run

Build LFHCal in `NewStructure/build`, enter an example directory, then:

```tcsh
yall-run validate
yall-run plan
```

To create a frozen campaign:

```tcsh
yall-run create
```

For production campaign records in the writable work area:

```tcsh
mkdir -p $LFHCAL_WORK/campaigns
yall-run create --campaigns-dir $LFHCAL_WORK/campaigns
```

Start the exact campaign directory printed by `create`.

The Condor examples use `tools/run-in-eic-container.sh` as their `%wrapper`. No LFHCal-specific provenance is embedded into ROOT files; yall-run keeps campaign, task, executable, input/output, scheduler, and attempt provenance in its campaign records.
