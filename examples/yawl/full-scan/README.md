# Full TB2026 HGCROC Yawl campaign

This example is the curated 44-file TB2026 parameter-setting study as one Condor/DAGMan campaign.

The Yawlfile itself defines the 44 raw runs and the 22 correlated pedestal/muon/ToA relationships. It does **not** discover the campaign by scanning whatever raw files happen to exist, and it no longer needs staging symlinks, pair-marker files, or a preparation script.

The processing chain is:

1. convert the 44 selected `Run*.h2g` files;
2. extract pedestal calibrations for the 22 pedestal/muon pairs;
3. transfer pedestal, bad-channel, and ToA corrections;
4. fit the initial MIP scale;
5. save the selected-MIP sample;
6. run three reduced MIP-refinement passes;
7. apply the final calibration;
8. extract waveform ROOT and histogram files;
9. build comparison lists and run the all/RF/CF/CFComp/CC waveform comparisons.

The scientific executables remain ordinary LFHCal programs. Yawl owns task dependencies, Condor submission, logs, output protection, and provenance JSON.

## Raw data location

Set the site-specific raw-data directory before loading the Yawlfile. On Paul's current BNL setup:

```tcsh
setenv LFHCAL_RAW /gpfs01/star/pwg/pnord/eic/2026TBdata
```

`@env LFHCAL_RAW` is resolved when Yawl parses the workflow and the resolved paths are frozen into `campaign.json`. Changing the environment variable later does not change an already-created campaign.

## Curated 22-pair study

The selected pedestal -> muon pairs are:

```text
296 -> 298   ToA 1
299 -> 300   ToA 1
303 -> 304   ToA 1
307 -> 308   ToA 1
309 -> 310   ToA 1
328 -> 329   ToA 2
330 -> 331   ToA 2
332 -> 333   ToA 2
334 -> 335   ToA 2
336 -> 337   ToA 2
338 -> 339   ToA 2
340 -> 341   ToA 2
342 -> 343   ToA 2
344 -> 345   ToA 2
346 -> 347   ToA 2
348 -> 349   ToA 2
350 -> 351   ToA 2
352 -> 353   ToA 2
354 -> 355   ToA 2
356 -> 357   ToA 2
358 -> 359   ToA 2
360 -> 361   ToA 2
```

This gives 44 distinct raw files. The set is intended to cover the nominal/reference setting and the useful RF, CC, CF, and CFComp variations without duplicate-setting repeats. In particular, 301 -> 302 is omitted because run 302 is the known bad/short file; 307 -> 308 is used for the duplicate RF=4 setting; and 354 -> 355 is used as the RF9/CF5/CC5/CFComp1 reference instead of duplicate 362 -> 363.

The resulting comparison groups are generated from the run database by `make-comparison-lists.py`:

- RF: nominal CF7/CC5/CFComp1 while RF varies;
- CC: nominal RF9/CF7/CFComp1 while CC varies;
- CF: nominal RF9/CC5/CFComp1 while CF varies;
- CFComp: RF9/CF5/CC5 while CFComp varies;
- all: all 22 muon runs.

## Create and inspect the campaign

Build LFHCal in `NewStructure/build`, then from this directory:

```tcsh
yawl-run validate
yawl-run plan
yawl-run create
```

The plan should contain 44 conversion tasks, 22 complete calibration/waveform chains, one comparison-list fan-in, and five final `CompareWaveform` tasks.

Start the exact campaign printed by `create`:

```tcsh
yawl-run start campaigns/<campaign-id>
```

Use:

```tcsh
yawl-run status campaigns/<campaign-id>
```

while it is running.

## Environment

The Yawlfile uses `../../../tools/run-in-eic-container.sh` as the Condor wrapper. Yawl archives and hashes that wrapper when the campaign is created.

No LFHCal-specific provenance is embedded into ROOT files. Campaign, executable, input/output, scheduler, and attempt records stay in Yawl's JSON files.
