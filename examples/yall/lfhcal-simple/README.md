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

This is the recommended first LFHCal integration test at BNL. It is intentionally **wrapper-free**. Run `yall-run` from inside `eic-shell`, as the original local example was designed. The later Condor examples instead run Yall on the host and wrap only the scientific payload.

## Setup

Use the BNL bootstrap described in [../SETUP.md](../SETUP.md). It defines:

```text
LFHCAL_DATA=/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata
LFHCAL_WORK=/gpfs01/star/scratch/<your-login-name>/lfhcal
EIC_SHELL=<your workspace>/eic-shell
```

From the normal BNL tcsh session:

```tcsh
cd "$LFHCAL_REPO/examples/yall/lfhcal-simple"
source env.tcsh
$EIC_SHELL
```

The bootstrap installs the same editable `yall-run` checkout for the host Python and for the Python inside `eic-shell`. Inside the EIC environment:

```bash
yall-run --help
yall-run validate
yall-run plan
yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns" -j 4 | yall-run start
```

This is a local Yall campaign. No Condor jobs are submitted.

## Why it stays small

The three pedestal/MIP pairs are:

```text
296 / 298
299 / 300
303 / 304
```

`Convert`, `DataPrep`, and `HGCROCStudy` are all limited to the first 1000 events. Outputs go under:

```text
$LFHCAL_WORK/lfhcal-simple/
```

This is deliberately not a production calibration. Its purpose is to establish that the real LFHCal software stack works end-to-end inside the EIC environment before testing the batch system.

When it succeeds, leave `eic-shell` and return to the normal BNL login shell. Then run the small Condor/EIC smoke test described in [../SETUP.md](../SETUP.md), followed by `scan-set-1`.
