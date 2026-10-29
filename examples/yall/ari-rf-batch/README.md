# Ari RF scan: BNL batch only

**Prepared, not run at BNL.** Use the native tcsh quick start below on the normal host, never inside an interactive EIC shell. Later Bash examples are explicitly marked. `yall-run start` submits HTCondor DAG jobs. Compilation, unit tests, conversion, calibration, waveform analysis, and comparison all run on execute nodes. The only host work is Git/setup, small-file provenance, raw file stat checks, graph validation, directory creation and submission/monitoring.

## Evidence and scope

The 13 runs are Ari's `RF_Scans_Waveform.C` inventory. Pedestal pairings are from `NewStructure/runHGCROCCalibration_TBSPSH2_2026.sh`, `calibMuonParScan`. Table rows carry `(pedestal, signal, ToA scan)`; the native `@each run in pairs.ped pairs.run` union deduplicates conversion across both columns. Pedestal preprocessing uses a separate unique `@each ped in pairs.ped`. Repeated pedestal tests explicitly verify sharing. The actual 13-run inventory has 13 different pedestals; none is invented/shared incorrectly.

Recovered Ari `master_waveform_analysis.sh`, `AUTOMATED_Waveform_Analysis_.sh` and its `helperCalibHGCROC.sh` confirm this chain, matching the repository `scan-set-1/Yallfile`: pedestal → BCTOA → default MIP calibration → saveNewMuon (`-X` in recovered helper) → three reduced event-tree refinements → fullMuon applied to the original selected MIP tree → waveform. Current helper has `-M` instead; this workflow deliberately uses recovered `-X`. It does not silently switch to `_red_woE` or raw/full calibration.

The May run DB is used, not the erroneous April DB in the legacy May application script. Early runs use ParamScan_1 ToA, later runs ParamScan_2; sumV2 mapping, OnlyCenter2x4 bad map and active parameter-scan cells are preserved. Current repository configurations are hashed at preparation, but have not been proved byte-identical to those used for Fredi's historical ROOT outputs. No manually modified per-run calibration override is applied. Confirm whether one is needed before running.

Peak-bin timing, bin-center FWHM and existing clock-shift behavior remain unchanged. This does **not** validate physics or complete the 13-run Excel comparison.

## Fresh isolated checkout

Choose a new shared-storage directory visible on submit host, execute nodes and inside the EIC container. Never reuse an existing analysis checkout or output directory.

```tcsh
set base = /gpfs01/star/scratch/pnord/ari-rf-`date -u +%Y%m%dT%H%M%SZ`
git clone --branch ari-rf-condor-pipeline --recurse-submodules https://github.com/paulnord/epic-lfhcal-tbana.git "$base/source"
set repo = "$base/source"
which condor_submit condor_submit_dag yall-run
printenv EIC_SHELL
```

This branch contains the inspected main plus PR19 and PR20, with the workflow installed. No manual merges, attachment downloads or pasted file bodies are needed. Stop on any command error. The fresh clone does not build or submit jobs. Record `git -C "$repo" rev-parse HEAD` with campaign results.

Use an existing host `yall-run` at least 0.12.0a7 including PR45. Actual parser tests here used commit `5a39498d023b1c9edcaa08926c80f2bb848efda9`. Record `yall-run --version` and the yall checkout SHA. No ROOT build on the login host.

### Native tcsh pilot preparation (no submission)

After `printenv EIC_SHELL` confirms your working launcher, review the recipe above, then:

```tcsh
python3 "$repo/examples/yall/ari-rf-batch/prepare.py" --destination "$base/pilot" --raw /gpfs01/star/pwg/pnord/eic/2026TBdata/raw --eic-shell "$EIC_SHELL" --mode pilot --accept-repo-scan-recipe
cd "$base/pilot"
yall-run validate
yall-run plan
```

If EIC_SHELL is unset, stop and identify the existing launcher; do not guess its path. Worker visibility and container identity still need pilot verification. When ready to submit (a separate explicit action):

```tcsh
set C = `yall-run create --campaigns-dir "$base/campaigns"`
yall-run start "$C"
yall-run status "$C"
```

The remaining examples use Bash syntax and are alternatives, not commands to paste directly into tcsh.

## Prepare and submit one complete-run pilot

The raw path below is historical documentation, not a confirmed mount. Replace `EIC` and `BASE` with real shared absolute paths. The generator requires all selected raw inputs and an executable launcher to exist locally; worker mounts still need pilot validation.

```bash
RAW=/gpfs01/star/pwg/pnord/eic/2026TBdata/raw
EIC=/absolute/shared/path/to/eic-shell
REPO="$BASE/source"
command -v condor_submit condor_submit_dag yall-run
python3 "$REPO/examples/yall/ari-rf-batch/prepare.py" \
  --destination "$BASE/pilot" --raw "$RAW" --eic-shell "$EIC" \
  --mode pilot --accept-repo-scan-recipe
cd "$BASE/pilot"
yall-run validate
yall-run plan | tee plan.txt
C=$(yall-run create --campaigns-dir "$BASE/campaigns")
printf '%s\n' "$C" | tee campaign-path.txt
yall-run start "$C"
yall-run status "$C"
```

Pilot is run298+ped296, **all events**, 13 DAG nodes; a truncated calibration would not be a useful scientific pilot. Check worker build/tests, all stages, ROOT files and RF summary/status plots. A single RF point is expected. Do not launch full until pilot completes successfully and resource/mount/config assumptions are checked.

## Full scan (after pilot review)

```bash
python3 "$REPO/examples/yall/ari-rf-batch/prepare.py" \
  --destination "$BASE/full" --raw "$RAW" --eic-shell "$EIC" \
  --mode full --accept-repo-scan-recipe
cd "$BASE/full"
yall-run validate
yall-run plan | tee plan.txt
C=$(yall-run create --campaigns-dir "$BASE/campaigns")
printf '%s\n' "$C" | tee campaign-path.txt
yall-run start "$C"
yall-run status "$C"
```

Full has 145 nodes: one build, 26 unique conversions, 13 pedestal extractions, 104 per-run downstream tasks and one summary fan-in. Each pilot/full workspace builds once; no binaries are built independently per run. Final products: `ari_rf_comparison.root`, `ari_rf_plots/`, `rf_inputs.txt`; intermediate data and plots under `products/`.

## Safety, provenance, logs, retries

Keep source, config, scripts, raw files and container image immutable from preparation until completion. `preparation.json` records source HEAD/diff, small-input SHA256 hashes and raw size/mtime (not a huge login-host hash pass). Build records compiler environment and decoder SHA in `build/environment.txt`; yall campaign captures expanded commands/graph and attempt logs/provenance. Preserve all of these with results. Pin/record the actual EIC image on BNL; its identity is not available here.

Defaults mirror existing scan examples: 1 CPU, 4GB RAM, 8GB disk, 2h; conversion 2GB RAM; build 2 CPUs. They are starting requests, not measured bounds. `%time` is a site-specific MaxRuntime convention; confirm BNL policy and tune after pilot. `%retry 0` intentionally avoids destructive automatic retries against partially written ROOT outputs. Inspect failed-node logs before recovery; safest retry is a fresh isolated workspace. Never add `-f`, erase outputs, or resume blindly. Generator refuses an existing destination. No job is submitted by `prepare.py`.

Tests: `PYTHONPATH=/path/to/yall-run/src python3 test_prepare.py`; no raw processing or scheduler required. These validate graph expansion, not BNL execution.

## Preparation safety fixes

The worker adapter is self-contained because yall copies it into the campaign. Preparation normalizes script paths through symlinks (including BNL /gpfs and /gpfs/mnt aliases), completes provenance first, then publishes a staged workspace. If an earlier preparation left a partial `pilot`, preserve it and use a new name such as `pilot-v2`. Recreate campaigns after updating scripts: already-created campaigns retain their archived wrapper.

## Isolated recovery after a downstream MIP plotting failure

`prepare_recovery.py` retains the old full campaign and its outputs unchanged.
It requires all 13 transfer tasks' **latest attempts** to have completed with
exit 0, the exact recorded pedestal/run/scan mapping and commands, the matching
archived recipe, and readable, nonempty transfer files whose size/mtime still
match those successful attempts. It refuses amended recipes, mismatched inputs,
and an existing destination or a destination inside the old workspace/campaign.
No raw files need to be converted again. Keep the old transfer files immutable.

Use a **separate fixed source checkout**, never update a source/build directory
that existing jobs might still use. With `REPO` set to that checkout and `C` to
the old campaign directory, this is native tcsh preparation syntax:

```tcsh
set OLD = /gpfs01/star/scratch/pnord/ari-rf-full-20261029T173654Z/full
set RECOVERY = /gpfs01/star/scratch/pnord/ari-rf-recovery-`date -u +%Y%m%dT%H%M%SZ`
python3 "$REPO/examples/yall/ari-rf-batch/prepare_recovery.py" --previous-workspace "$OLD" --campaign "$C" --destination "$RECOVERY" --eic-shell /star/u/pnord/bin/eic-shell
cd "$RECOVERY"
yall-run validate
yall-run plan
```

These commands only prepare/inspect; they do not submit or cancel jobs. Check
old campaign status before any later submission; this helper does not stop jobs
or claim that the old campaign is quiescent. Review the new 93-node graph:
new build + 13×(MIP, selection, three refinements, calibration, waveform) +summary.
It reuses the 52 successful conversion/pedestal/transfer tasks' products without
changing any historical downstream scientific options. Every new output is
isolated; partial failed MIP files are neither consumed nor deleted.

The build worker runs existing build/tests and then opens all 13 transfer files
**read-only**, rejects zombie/recovered files, and checks nonempty Setup, Data,
Calib trees and setup/event/calib branches. Any failure blocks MIP descendants.
It prints tree entry counts in the build log. This is structural verification,
not a full event scan or proof of calibration/scientific validity. It does not
run ROOT on the login host. `recovery.json` records the original campaign/source,
recipe/manifest/attempt hashes, input file stats and new source/config provenance.

Tests: `PYTHONPATH=/path/to/yall-run/src python3 test_prepare_recovery.py`.
The parser/campaign tests use real yall schema but synthetic files; optional
PyROOT tests create tiny ROOT files and test valid/missing/corrupt structures.
No test submits jobs or uses BNL raw data.
