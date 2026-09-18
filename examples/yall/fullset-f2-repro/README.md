# FullSet F2 reproduction

This example reproduces Fredi's SPS H2 `FullSetF_2` calibration chain from raw
TB2026 data using Yall and HTCondor.

It is a larger validation workflow, not the recommended first Yall/LFHCal test.
For a fresh BNL setup, complete the checks in [`../SETUP.md`](../SETUP.md)
first.

For the numerical comparison with the published calibration, see
[`CALIBRATION_COMPARISON.md`](CALIBRATION_COMPARISON.md).

## Inputs

The workflow uses pedestal run `471` and merges muon runs
`472`, `475`, `476`, `479`, `480`, and `483` as `Muon_FullSetF_2`.

The raw inputs must be readable as:

```text
$LFHCAL_DATA/Run471.h2g
$LFHCAL_DATA/Run472.h2g
$LFHCAL_DATA/Run475.h2g
$LFHCAL_DATA/Run476.h2g
$LFHCAL_DATA/Run479.h2g
$LFHCAL_DATA/Run480.h2g
$LFHCAL_DATA/Run483.h2g
```

The Yallfile also uses the TB2026 mapping and run database, the FullSetA-F bad
channel map, and the published FullSetF ToA offsets. The ToA offsets are not
rederived by this workflow.

## Run table and dependencies

The Yallfile declares the seven runs once in a typed
`@table runs type run:` table. One `convert-{type}-{run}` family converts every
row. `merge-muon` binds `type=muon`, restricting both its patterned parent
fan-in and `@input.parts` to runs `472`, `475`, `476`, `479`, `480`, and `483`;
pedestal run `471` cannot leak into the merge.

The `{type}-{run}` pedestal family uses `@each type pedestal`. That explicitly
binds only `type`; the compatible `convert-{type}-{run}` parent supplies the
remaining `run=471`, producing `pedestal-471`. `transfer-f2` depends on the
patterned pedestal family, so changing the pedestal row makes the conversion,
pedestal task, and transfer dependency follow it automatically.

This partial-binding syntax requires yall-run PR #33, merged as commit
`1081e9dd39418262588248272618130ce0503b8a`.

## Run at BNL

Use the normal BNL `tcsh` login/submit session. Yall and Condor run on the host;
the scientific payloads are sent through the configured EIC shell wrapper.

```tcsh
cd "$LFHCAL_REPO/examples/yall/fullset-f2-repro"
source env.tcsh
```

Check the raw inputs before submitting:

```tcsh
foreach r (471 472 475 476 479 480 483)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
```

Validate and inspect the graph:

```tcsh
yall-run validate
yall-run plan
```

Create and submit a campaign:

```tcsh
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

Repeat `yall-run status "$C"` to inspect progress.

Do not start another campaign against an existing output tree. Use a fresh
`LFHCAL_WORK` for a clean rerun.

## Outputs

Results are written under:

```text
$LFHCAL_WORK/fullset-f2-repro/
```

The workflow converts the seven raw runs, constructs the pedestal calibration,
merges and calibrates the muon sample, selects MIP-triggered events, and performs
five reduced/no-event-tree refinement passes through `Imp5R`.

The final products are:

```text
$LFHCAL_WORK/fullset-f2-repro/final/calib_Final_Muon_FullSetF_2.root
$LFHCAL_WORK/fullset-f2-repro/final/calib_Final_Muon_FullSetF_2_calib.txt
```

`final-f2` does not perform another fit; it copies the `Imp5R` products into the
final output directory.

Campaign records and scheduler logs are kept under `$LFHCAL_WORK/campaigns` when
the commands above are used.
