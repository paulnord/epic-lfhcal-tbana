# Simple LFHCal Yall example

Start here for the LFHCal examples. This is a bounded smoke test of the real
LFHCal programs, not a production calibration.

The example uses three pedestal/MIP pairs:

```text
296 / 298
299 / 300
303 / 304
```

It creates the output directories with a Yall `%preflight`, then schedules:

1. six unique raw-run conversions;
2. three pedestal extractions.

That is **9 scheduled tasks**. Conversion and pedestal extraction are both
limited to the first 1000 events.

## Run it

Use the BNL setup described in [../SETUP_TLDR.md](../SETUP_TLDR.md). From the
normal BNL tcsh session:

```tcsh
cd "$LFHCAL_REPO/examples/yall/lfhcal-simple"
source env.tcsh
$EIC_SHELL
```

Inside `eic-shell` (bash):

```bash
source ./env-eic.sh
yall-run validate
yall-run plan
C=$(yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns" -j 1)
yall-run start "$C"
yall-run status "$C"
```

The `create` command runs the lightweight directory-creation preflight locally.
No Condor job is submitted for setup. The campaign itself uses the local backend.

Outputs go under:

```text
$LFHCAL_WORK/lfhcal-simple/
```

When it succeeds, exit from `eic-shell` and run the small Condor/EIC smoke test
described in [../SETUP_TLDR.md](../SETUP_TLDR.md), followed by `scan-set-1`.
