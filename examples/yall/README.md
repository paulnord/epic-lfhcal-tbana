# Yall examples

These examples show how to run existing LFHCal executables with `yall-run` without adding provenance code to the C++ applications.

The Condor examples require **yall-run 0.9.0 or newer** for wrapper arguments.

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

## Condor environment

Use the same installed `eic-shell` launcher that you use to build LFHCal. Set its path on the **host**, outside the container:

```bash
export EIC_SHELL="$HOME/eic/eic-shell"
```

For tcsh:

```tcsh
setenv EIC_SHELL "$HOME/eic/eic-shell"
```

Before submitting work, verify the launcher's reliable non-interactive interface:

```bash
echo 'root-config --version' | "$EIC_SHELL"
echo 'python3 --version' | "$EIC_SHELL"
```

The current container-side `eic-shell` runs argv-style commands through `bash -c "$@"`, which does not preserve ordinary multi-argument commands. The Condor Yallfiles therefore use the portable `tools/run-in-eic-shell.sh` adapter. It shell-quotes the worker argv and sends one complete command to `eic-shell` on standard input.

The production workflows also set the ROOT/OpenMP thread limits inside the EIC environment to match their one-CPU requests:

```text
@env EIC_SHELL
%wrapper ../../../tools/run-in-eic-shell.sh {EIC_SHELL} \
    /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1
```

Yall archives the adapter and freezes the selected `EIC_SHELL` path and thread-limit arguments. The selected launcher itself must remain visible on the worker nodes and must reference a container runtime, installation, image and bind paths available there. The campaign directory, raw data, work area and LFHCal build must also be visible there. Do not use host-local `/tmp` for a Condor campaign or its products.

Archiving the adapter does not snapshot the container image. Select a fixed image for reproducible work, and use that same environment for compilation and worker execution. A launcher that points to `nightly` still uses a moving image.

Before a large campaign, run the small `examples/eic-shell` smoke example in the yall-run repository to check the launcher on your batch nodes. CERN execution still needs site testing.

## Inspect and run

Build LFHCal in `NewStructure/build` inside `eic-shell`. Run local examples inside that environment; create and submit Condor campaigns from the **host shell**.

Enter an example directory, then:

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

Start the exact campaign directory printed by `create`. In bash, the complete creation/submission sequence is:

```bash
CAMPAIGN=$(yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns") &&
yall-run start "$CAMPAIGN" &&
yall-run status "$CAMPAIGN"
```

Use a fresh `LFHCAL_WORK` for a new production run. A new campaign ID does not change the output paths; existing declared outputs are protected by default.

No LFHCal-specific provenance is embedded into ROOT files; yall-run keeps campaign, task, executable, input/output, scheduler, and attempt provenance in its campaign records.
