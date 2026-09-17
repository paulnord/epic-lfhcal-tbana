# Simple LFHCal Yall example

Start here for the LFHCal examples.

If Yall is new to you, first skim the
[yall-run Quick start](https://github.com/paulnord/yall-run/blob/main/docs/QUICKSTART.md).
It introduces the `validate -> plan -> create -> start -> status` lifecycle used
below.

This Yallfile demonstrates three common workflow patterns without trying to describe a full production analysis:

1. Convert every unique run from a top-level pedestal/MIP table.
2. Fit each pedestal once and calibrate the correlated pairs.
3. Create summaries from the MIP column, without repeating the run list.

The `pairs` table is the single source of run numbers. `@each run in pairs.ped pairs.mip` creates one conversion per unique run, even when a pedestal is shared. Pedestal fitting waits only for its own conversion; each calibration waits for its pedestal fit and MIP conversion. Summaries wait only for their own conversion. There is no all-conversions barrier. The default example has 16 tasks.

This example is also the recommended **first LFHCal integration test at BNL**. It runs with Yall's local backend from the normal login shell, while each LFHCal payload is wrapped in `eic-shell`. It therefore checks the actual LFHCal executables, shared raw data, the EIC environment, Yall dependencies, and scratch output before involving Condor.

## Setup

Use the BNL bootstrap described in [../SETUP.md](../SETUP.md). It defines:

```text
LFHCAL_DATA=/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata
LFHCAL_WORK=/gpfs01/star/scratch/<your-login-name>/lfhcal
EIC_SHELL=<your workspace>/eic-shell
```

From this directory:

```tcsh
source env.tcsh
yall-run validate
yall-run plan
```

The campaign uses the local backend. Stay in the normal BNL shell; do not enter `eic-shell` interactively. The Yallfile applies the same payload wrapper used by the production Condor workflows.

To run up to four dependency-ready tasks at once:

```tcsh
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns" -j 4`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

Use `set C = ...`, not `setenv C`, for the campaign handle in tcsh.

## Why it stays small

The three pedestal/MIP pairs are:

```text
296 / 298
299 / 300
303 / 304
```

`Convert`, `DataPrep`, and `HGCROCStudy` are all limited to the first 1000 events. The outputs go under:

```text
$LFHCAL_WORK/lfhcal-simple/
```

This is deliberately not a production calibration. Its purpose is to establish that the real LFHCal software stack works end-to-end locally before testing the batch system.

After this succeeds, run the small Condor/EIC smoke test described in [../SETUP.md](../SETUP.md), then move on to `scan-set-1`.
