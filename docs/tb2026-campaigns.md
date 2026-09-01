# TB2026 campaign generators

Campaign generators decide which analysis commands should run and how those
commands depend on one another. They write the same plain-text manifest used by
both local execution and HTCondor DAGMan. They do **not** execute or submit the
campaign.

Every generated file is intended to be read before it is run. It contains
complete `JOB`, `PARENT ... CHILD ...`, and `RETRY` records with fully expanded
paths and explicit input/output lineage.

## Choose a generator

| Goal | Generator | Per-run chain |
|---|---|---|
| Convert raw files only | `make-tb2026-conversion-campaign` | `Convert` |
| Create a calibration | `make-tb2026-paramscan-campaign` | full pedestal/muon calibration chain |
| Analyze many runs with an existing calibration | `make-tb2026-analysis-campaign` | `Convert` → `DataPrep -C` → `HGCROCStudy` |

Use `--help` on a generator for its complete option list. Run and Condor
resource options belong to `lfhcal-run`, not to the generators.

## Conversion-only campaign

Individual runs and inclusive ranges can be mixed:

```console
python3 tools/make-tb2026-conversion-campaign \
  --raw-dir /path/to/2026TBdata \
  --output-dir /path/to/converted \
  --manifest convert-137-178.txt \
  --check \
  137 138-149 153 159 165 178
```

The manifest has one small `prepare` node and one independent `Convert` node
per run. Once preparation succeeds, local `-j N` execution or Condor may run
all conversions independently.

## Existing calibration plus many data runs

Supply the final calibration ROOT file with `--calibration`. The bad-channel
map, ToA offsets, run database, mapping, and active-cell list use TB2026
defaults but each has an override option.

```console
python3 tools/make-tb2026-analysis-campaign \
  --raw-dir /path/to/2026TBdata \
  --output-dir /path/to/analysis-137-178 \
  --calibration /path/to/rawHGCROC_wPedwMuon_wBC_Imp3R_298.root \
  --manifest analysis-137-178.txt \
  --check \
  137 138-149 153 159 165 178
```

For each run the generator emits:

```text
convert-RUN → apply-calibration-RUN → waveform-RUN
```

The branches share only the `prepare` node and the declared calibration/config
inputs. There are no dependencies between data runs, so each branch may
progress independently.

The calibration command follows the repository's established `Calib full`
path in `NewStructure/helperCalibHGCROC.sh`: `DataPrep -C` is applied directly
to the converted `rawHGCROC_RUN.root`, followed by `HGCROCStudy -w` on the
calibrated output.

## Inspect, run, or submit

Inspect the generated manifest first:

```console
less analysis-137-178.txt
```

Run locally with at most four simultaneous jobs:

```console
python3 tools/lfhcal-run -j 4 analysis-137-178.txt
```

Or submit exactly the same graph through Condor DAGMan from the BNL submit
host:

```console
python3 tools/lfhcal-run \
  --condor \
  --condor-wrapper tools/run-in-eic-container.sh \
  --environment-file /star/u/USER/eic-2026/eic-env/eic-shell \
  --container-image /star/u/USER/eic-2026/eic-env/local/lib/eic_xl-nightly \
  --request-memory 4GB \
  analysis-137-178.txt
```

`-j` is intentionally local-only. Condor controls when independent DAG nodes
run; `--request-cpus` controls CPUs requested by each Condor job.

## Safety checks

`--check` verifies the built executables, shared configuration, calibration,
and all `RunNNN.h2g` inputs before writing the manifest. Without `--check`, a
manifest can be prepared before all inputs arrive. Existing manifests are not
overwritten unless `--force` is supplied.

All three generators use the shared `tools/lfhcal_campaign.py` manifest
builder. New workflow-specific generators should use that builder rather than
constructing shell text or implementing another scheduler.
