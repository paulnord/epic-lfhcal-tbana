# FullSet F1 reproduction

This example reproduces Fredi's SPS H2 `FullSetF_1` calibration chain from raw
TB2026 data using Yall and HTCondor.

It is a larger validation workflow, not the recommended first Yall/LFHCal test.
For a fresh BNL setup, complete the checks in [`../SETUP.md`](../SETUP.md)
first.

## Inputs

The workflow uses pedestal run `431` and merges muon runs `426` through `430`
as `Muon_FullSetF_1`.

The raw inputs must be readable as `$LFHCAL_DATA/Run<run>.h2g` for runs
`426 427 428 429 430 431`.

The Yallfile also uses the TB2026 mapping and run database, the FullSetA-F bad
channel map, and the published FullSetF ToA offsets.

Fredi's published reference calibration is:

```text
calibrations/TB2026/calib_SPS-H2_FullSetF_1.txt
```

## Run table and dependencies

The Yallfile declares the six runs once in a typed
`@table runs type run:` table. One `convert-{type}-{run}` family converts every
row. `merge-muon` binds `type=muon`, restricting both its patterned parent
fan-in and `@input.parts` to runs `426`–`430`; pedestal run `431` cannot leak
into the merge.

The `{type}-{run}` pedestal family uses `@each type pedestal`. That explicitly
binds only `type`; the compatible `convert-{type}-{run}` parent supplies the
remaining `run=431`, producing `pedestal-431`. `transfer-f1` depends on the
patterned pedestal family, so changing the pedestal row makes the conversion,
pedestal task, and transfer dependency follow it automatically.

This partial-binding syntax requires yall-run PR #33, merged as commit
`1081e9dd39418262588248272618130ce0503b8a`.

## Run at BNL

Use the normal BNL `tcsh` login/submit session:

```tcsh
cd "$LFHCAL_REPO/examples/yall/fullset-f1-repro"
source env.tcsh
foreach r (426 427 428 429 430 431)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

Repeat `yall-run status "$C"` to inspect progress. Do not start a second
campaign against an existing output tree; use a fresh `LFHCAL_WORK` for a clean
rerun.

## Outputs

Results are written under:

```text
$LFHCAL_WORK/fullset-f1-repro/
```

The workflow converts the six raw runs, builds the pedestal calibration, merges
the muon sample, applies bad-channel and ToA information, selects MIP-triggered
events, and performs five refinement passes through `Imp5R`.

Final products are:

```text
$LFHCAL_WORK/fullset-f1-repro/final/calib_Final_Muon_FullSetF_1.root
$LFHCAL_WORK/fullset-f1-repro/final/calib_Final_Muon_FullSetF_1_calib.txt
```

`final-f1` does not perform another fit; it copies the `Imp5R` products into the
final output directory.
