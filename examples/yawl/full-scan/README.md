# Full TB2026 HGCROC Yawl campaign

This example turns the parameter-scan analysis into one Condor/DAGMan campaign:

1. convert every staged `Run*.h2g` file;
2. extract pedestal calibrations for every complete pedestal/muon pair;
3. transfer pedestal, bad-channel, and ToA corrections;
4. fit the initial MIP scale;
5. save the selected-MIP sample;
6. run three reduced MIP-refinement passes;
7. apply the final calibration;
8. extract waveform ROOT and histogram files;
9. build comparison lists and run the all/RF/CF/CFComp/CC waveform comparisons.

The scientific executables remain ordinary LFHCal programs. Yawl owns task dependencies, Condor submission, logs, retries, output protection, and provenance JSON.

## Prepare the raw-file set

The example deliberately does not hard-code a storage location. Stage the exact raw files for a study as symlinks:

```bash
mkdir -p raw
ln -s /path/to/selected/Run*.h2g raw/
```

For the 44-file campaign, verify the staged count and create the pair markers used by Yawl pattern expansion:

```bash
./prepare-study.py --expect-raw 44
```

`prepare-study.py` reads `parameter-scan-pairs.tsv` and creates a marker only when both members of a canonical pedestal/muon pair are present. It also reports staged runs that are not part of a complete pair. Run it before `yawl-run create`, because `@each` inputs are frozen at campaign creation.

## Build and inspect

Build LFHCal in `NewStructure/build`, then from this directory:

```bash
yawl-run validate
yawl-run plan
yawl-run create
```

The plan should contain one conversion task for every staged raw file, one calibration/waveform chain for every complete pair, and five final `CompareWaveform` tasks.

Start the exact campaign printed by `create`:

```bash
yawl-run start campaigns/<campaign-id>
```

Use `yawl-run status campaigns/<campaign-id>` while it is running.

## Environment

The Yawlfile uses `../../../tools/run-in-eic-container.sh` as the Condor wrapper. Yawl archives and hashes that wrapper when the campaign is created. The wrapper enters the EIC container and keeps ROOT/OMP thread counts at one by default.

The default container alias is `eic_xl:nightly`; that alias is still mutable. Pinning exact container identity is a separate provenance improvement.

No LFHCal-specific provenance is embedded into ROOT files. Campaign, executable, input/output, scheduler, and attempt records stay in Yawl's JSON files.
