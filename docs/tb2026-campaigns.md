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
| Test one pedestal/muon calibration pair | `make-tb2026-paramscan-campaign` | full parameter-scan calibration chain |
| Calibrate once and analyze many data runs | `make-tb2026-analysis-campaign` | build calibration → per-run `Convert` → `DataPrep -C` → `HGCROCStudy` |

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

## Calibration plus many data runs

Provide one pedestal run, all muon runs that form the calibration sample, and
the data runs to analyze. The generator converts every required raw file,
merges the muon ROOT files, builds and refines one calibration, then applies
that calibration independently to each data run. Because bad-channel and ToA
corrections change between detector configurations, they must be selected
explicitly. The run database and mapping use TB2026 SPS H2 defaults.

This FullSetC example uses pedestal 137, muon runs 138 through 149, and four
representative 50 GeV data runs:

```console
python3 tools/make-tb2026-analysis-campaign \
  --raw-dir /path/to/2026TBdata \
  --output-dir /path/to/fullsetc-analysis \
  --pedestal-run 137 \
  --muon-runs 138-149 \
  --calibration-name FullSetC_1 \
  --bad-channels configs/TB2026/badChannel_HGCROC_SPSTB2026_dummy.txt \
  --toa-offsets configs/TB2026/ToAOffsets_TBSPS2026_FullSetC.csv \
  --manifest fullsetc-analysis.txt \
  --check \
  153 159 165 178
```

The shared calibration section converts the pedestal and all muons, merges the
muon ROOT files, transfers pedestal/bad-channel/ToA information, performs the
initial muon calibration and MIP selection, runs four reduced refinements, and
writes `calib_FullSetC_1.root`.

Each data branch can convert while calibration is being built, then waits for
the final shared calibration:

```text
convert-RUN + shared calibration → apply-calibration-RUN → waveform-RUN
```

The default is four reduced MIP-calibration refinement rounds, matching the
established FullSetC workflow. Use `--refinement-rounds N` when a detector
configuration requires a different count. An active-cell list is optional;
without one, waveform analysis does not add an `-l` restriction.

## Inspect, run, or submit

Inspect the generated manifest first:

```console
less fullsetc-analysis.txt
```

Run locally with at most four simultaneous jobs:

```console
python3 tools/lfhcal-run -j 4 fullsetc-analysis.txt
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
  fullsetc-analysis.txt
```

`-j` is intentionally local-only. Condor controls when independent DAG nodes
run; `--request-cpus` controls CPUs requested by each Condor job.

## Safety checks

`--check` verifies the built executables, selected configuration, and every
pedestal, muon, and data `RunNNN.h2g` input before writing the manifest.
Without `--check`, a manifest can be prepared before all inputs arrive.
Existing manifests are not overwritten unless `--force` is supplied.

All three generators use the shared `tools/lfhcal_campaign.py` manifest
builder. New workflow-specific generators should use that builder rather than
constructing shell text or implementing another scheduler.
