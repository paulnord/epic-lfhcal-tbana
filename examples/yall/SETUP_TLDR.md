# BNL setup — TL;DR

## New installation: start here

The easiest path is the installer below. It installs **yall-run**, gets the
LFHCal review branch, installs `eic-shell`, builds LFHCal, and writes the small
activation files used by the examples. It submits no jobs.

Run from the normal BNL **tcsh** login/submit shell:

```tcsh
mkdir -p "$HOME/lfhcal-yall-review"
cd "$HOME/lfhcal-yall-review"

curl -fL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration-upstream/tools/bootstrap-yall-integration.sh \
    -o bootstrap-yall-integration.sh

less bootstrap-yall-integration.sh

env LFHCAL_REPO_URL=https://github.com/paulnord/epic-lfhcal-tbana.git \
    LFHCAL_BRANCH=yall-integration-upstream \
    bash bootstrap-yall-integration.sh
```

Then:

```tcsh
source ./activate.tcsh
```

Raw input defaults to:

```text
/gpfs01/star/pwg/pnord/eic/2026TBdata/raw
```

and output goes under your personal scratch area.

Already have LFHCal installed using Fredi's instructions? **Do not install it
again.** Use the separate [existing-installation instructions](EXISTING_INSTALL.md).

## Small local test

From host tcsh:

```tcsh
cd "$LFHCAL_REPO/examples/yall/lfhcal-simple"
source env.tcsh

foreach r (296 298 299 300 303 304)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end

$EIC_SHELL
```

Inside **eic-shell (bash)**:

```bash
source ./env-eic.sh
yall-run validate
yall-run plan

C=$(yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns" -j 1)
yall-run start "$C"
yall-run status "$C"
exit
```

Expect **9 completed tasks**: six conversions and three pedestal extractions.
Directory creation runs as a `%preflight` during `create`, so it does not consume
a scheduler task. The test uses 1,000 events and does no MIP fitting.

## Small Condor test

Back on the host:

```tcsh
cd "$YALL_RUN_REPO/examples/eic-shell"
yall-run validate
yall-run plan

set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C" -vv
```

When that succeeds, continue with `examples/yall/scan-set-1`.

Full explanations: [SETUP.md](SETUP.md).
