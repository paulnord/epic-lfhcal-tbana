# BNL setup — TL;DR

**Install once → small local test → small Condor test → scan-set-1.**
Use the host **tcsh** shell except for the explicitly marked EIC-shell block.
Stop on errors. Full explanations: [SETUP.md](SETUP.md).

Already installed with the bootstrap? **Skip step 1.** Already have LFHCal in
another layout? Use [the existing-installation instructions](QUICKSTART.md#existing-installation-do-not-run-the-bootstrap-just-to-submit), not a second bootstrap.

## 1. First-time installation only

This is the current review branch. `lfhcal-yall-review` is just an example
parent workspace name, not a second repository or required directory name.
The installer installs yall-run and builds LFHCal; it submits no jobs.

```tcsh
mkdir -p "$HOME/lfhcal-yall-review"
cd "$HOME/lfhcal-yall-review"
curl -fL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration-upstream/tools/bootstrap-yall-integration.sh -o bootstrap-yall-integration.sh
less bootstrap-yall-integration.sh
env LFHCAL_REPO_URL=https://github.com/paulnord/epic-lfhcal-tbana.git LFHCAL_BRANCH=yall-integration-upstream bash bootstrap-yall-integration.sh
```

After the contribution is merged, use [the upstream installation block](SETUP.md#install-in-a-new-workspace) instead—not an additional installation.

## 2. Activate and check

From your bootstrap workspace (adjust the first path if necessary):

```tcsh
cd "$HOME/lfhcal-yall-review"
source ./activate.tcsh
which yall-run
which condor_submit
which condor_submit_dag
echo 'root-config --version' | "$EIC_SHELL"
python3 "$LFHCAL_REPO/examples/yall/check_shared_conversions.py" -v
```

Raw input defaults to **`/gpfs01/star/pwg/pnord/eic/2026TBdata/raw`**. This must
be the directory directly containing `Run*.h2g`, not the parent with `raw/`,
`converted/`, and `merged/`. You need read access. Set a different `LFHCAL_DATA`
in your environment or `site-env.tcsh` when necessary. For an older installation
pointing at the parent or using the extra mount prefix, use
[the one-time path fix](SETUP.md#already-installed-with-the-old-raw-data-path).
Pulling the repository does not rewrite your existing `site-env.tcsh`.

For an independent rerun, choose a fresh scratch output root **before** creating
campaigns. This does not install or rebuild software:

```tcsh
setenv LFHCAL_WORK "/gpfs01/star/scratch/`id -un`/lfhcal-onboarding-`date -u +%Y%m%dT%H%M%SZ`"
```

## 3. Small local detector test

Use a site-approved interactive allocation. From host tcsh:

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
ls -lh "$LFHCAL_DATA"/Run{296,298,299,300,303,304}.h2g
yall-run validate
yall-run plan
C=$(yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns" -j 1)
yall-run start "$C"
yall-run status "$C"
exit
```

Expect **10 completed tasks**: directory preparation, six conversions, three
pedestal extractions. The event limit is 1,000; there are no MIP fits or build
tasks. Products: `$LFHCAL_WORK/lfhcal-simple`; campaign logs: `$LFHCAL_WORK/campaigns`.

## 4. Small Condor/EIC test — back on the host

```tcsh
cd "$YALL_RUN_REPO/examples/eic-shell"
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C" -vv
```

This uses no detector data. Wait for all three tasks to complete before step 5.
Never submit Condor jobs from inside eic-shell.

## 5. First full workflow

```tcsh
cd "$LFHCAL_REPO/examples/yall/scan-set-1"
source env.tcsh
foreach r (296 298 299 300 303 304 307 308 309 310)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C" > "$LFHCAL_WORK/campaign-path.txt"
yall-run start "$C"
yall-run status "$C" -vv
```

Check inputs and resources before `create`. Results: `$LFHCAL_WORK/scan-set-1`.
Save the campaign path. Fix failures before `resume`; use a fresh work root for
an independent run. **Do not rerun the bootstrap or rebuild merely to run again.**
