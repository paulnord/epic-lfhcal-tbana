# FullSet G1 reproduction

This example reproduces Fredi's SPS H2 `FullSetG_1` calibration chain from raw
TB2026 data using Yall and HTCondor.

It is a larger validation workflow, not the recommended first Yall/LFHCal test.
For a fresh BNL setup, complete the checks in [`../SETUP.md`](../SETUP.md)
first.

## Inputs

The workflow uses pedestal run `485` and merges muon runs
`484`, `486`, `487`, `488`, `489`, `490`, and `491` as
`Muon_FullSetG_1`.

Set G uses the V1 summing-board mapping, the FullSetG bad-channel map, and the
published FullSetG ToA offsets.

The raw inputs must be readable as:

```text
$LFHCAL_DATA/Run484.h2g
$LFHCAL_DATA/Run485.h2g
$LFHCAL_DATA/Run486.h2g
$LFHCAL_DATA/Run487.h2g
$LFHCAL_DATA/Run488.h2g
$LFHCAL_DATA/Run489.h2g
$LFHCAL_DATA/Run490.h2g
$LFHCAL_DATA/Run491.h2g
```

The published reference calibration is:

```text
calibrations/TB2026/calib_SPS-H2_FullSetG_1.txt
```

## Run at BNL

Use the normal BNL `tcsh` login/submit session:

```tcsh
cd "$LFHCAL_REPO/examples/yall/fullset-g1-repro"
source env.tcsh

yall-run validate
yall-run plan

set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

Repeat `yall-run status "$C"` to inspect progress.

Results are written under:

```text
$LFHCAL_WORK/fullset-g1-repro/
```

The final products are:

```text
$LFHCAL_WORK/fullset-g1-repro/final/calib_Final_Muon_FullSetG_1.root
$LFHCAL_WORK/fullset-g1-repro/final/calib_Final_Muon_FullSetG_1_calib.txt
```

The run configuration is declared once near the top of the Yallfile with named
`@list` declarations. The merge task fans in the `convert-muon-{run}` family,
so its dependency and input lists follow the declared muon set automatically.
