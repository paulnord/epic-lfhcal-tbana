# BNL setup: local LFHCal test, Condor test, then scan-set-1

**[TL;DR — the commands to install and run the small tests](SETUP_TLDR.md)**  
Install once → local detector test → Condor/EIC test → scan-set-1.

Use the normal BNL tcsh login/submit session for installation and Condor work.
The small `lfhcal-simple` test is deliberately wrapper-free and runs inside
`eic-shell` (bash). Do not submit Condor jobs from inside the container.

For an existing installation or another site, start with [QUICKSTART.md](QUICKSTART.md).
Yall is optional; it does not replace the analysis software or change its fitter.

## Install in a new workspace

The installer creates/updates checkouts and builds LFHCal. It is not the command
to use merely to start another campaign. Use a new workspace for this preview,
not a checkout used by running jobs. Commands below download the installer to a
file so it can be inspected before execution.

The two installation blocks below are alternatives. The directory names are
examples of a parent workspace, not required names; do not run both blocks.
An existing bootstrap installation can skip directly to the preflight checks.

**Before this contribution is merged upstream**, use the review branch explicitly:

```tcsh
mkdir -p "$HOME/lfhcal-yall-review"
cd "$HOME/lfhcal-yall-review"
curl -fL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration-upstream/tools/bootstrap-yall-integration.sh -o bootstrap-yall-integration.sh
less bootstrap-yall-integration.sh
env LFHCAL_REPO_URL=https://github.com/paulnord/epic-lfhcal-tbana.git LFHCAL_BRANCH=yall-integration-upstream bash bootstrap-yall-integration.sh
```

**After upstream merges this contribution**, a fresh installation can use:

```tcsh
mkdir -p "$HOME/lfhcal-yall"
cd "$HOME/lfhcal-yall"
curl -fL https://raw.githubusercontent.com/eic/epic-lfhcal-tbana/main/tools/bootstrap-yall-integration.sh -o bootstrap-yall-integration.sh
less bootstrap-yall-integration.sh
bash bootstrap-yall-integration.sh
```

The installer defaults to `eic/epic-lfhcal-tbana` on `main` and
`paulnord/yall-run` on `main`. `LFHCAL_REPO_URL`, `LFHCAL_BRANCH`,
`YALL_REPO_URL`, `YALL_BRANCH`, and `LFHCAL_BUILD_JOBS` override those defaults.
`--prefix /path/to/workspace` overrides the installation directory. It initializes
the decoder submodule at the revision recorded by LFHCal, installs yall-run for
the host Python with `pip --user -e`, and builds LFHCal in the EIC environment.
It does not install Condor or upgrade pip.

The layout is:

```text
workspace/
    eic-shell
    yall-run/
    epic-lfhcal-tbana/
    activate.tcsh
    site-env.tcsh
```

Inside the interactive EIC shell, `lfhcal-simple/env-eic.sh` uses the yall-run
source checkout with the container's Python. There is no separate container pip
installation. The `.sh` installer and payload wrapper are implementation scripts,
not instructions to change the host login shell.

## Storage: shared input, personal output

New BNL installations default to:

```text
LFHCAL_DATA=/gpfs01/star/pwg/pnord/eic/2026TBdata/raw
LFHCAL_WORK=/gpfs01/star/scratch/<your-login-name>/lfhcal
```

`LFHCAL_DATA` must name the directory directly containing `Run*.h2g`, not its
parent. The shared data area now has `raw/`, `converted/`, and `merged/`
subdirectories; these recipes read the raw files and write new products under
`LFHCAL_WORK`. They do not modify the shared converted or merged data.

The shared PWG path is a site-specific convenience, not part of the distribution
and not guaranteed readable by every collaborator. Obtain access or set
`LFHCAL_DATA` to your own complete input files. Setup does not write into that
input directory or change its permissions. Edit `site-env.tcsh` for other paths;
existing settings are preserved. Do not append an example name to `LFHCAL_WORK`:
the Yallfiles do that themselves.

The work root, software, inputs, campaign records and EIC launcher must be visible
on worker nodes and inside the container. For a second run, use a fresh work root
rather than letting two campaigns write to the same output paths.

### Already installed with the old raw-data path?

Older setup versions used the parent `2026TBdata` directory, sometimes with
an extra `/gpfs/mnt` prefix. The raw files are now under `2026TBdata/raw`.
A pull updates defaults, but intentionally does not rewrite your generated
`site-env.tcsh` outside the repository. Correct only the old shared-data values,
retaining all other settings and a backup (BNL/Linux, host tcsh):

```tcsh
setenv LFHCAL_DATA "/gpfs01/star/pwg/pnord/eic/2026TBdata/raw"
sed -i.bnl-raw-backup -E 's|"/(gpfs/mnt/)?gpfs01/star/pwg/pnord/eic/2026TBdata(/raw)?"|"/gpfs01/star/pwg/pnord/eic/2026TBdata/raw"|g' "$LFHCAL_HOME/site-env.tcsh"
```

Run this migration once; choose another backup suffix if that backup already
exists. The replacement matches complete double-quoted values; it does not
append a second `/raw`. No reinstall or C++ rebuild is needed. Keep custom data
locations as chosen; do not rewrite arbitrary paths or old campaign/provenance
records. Verify the required files both on the host and inside eic-shell.

## 1. Preflight checks

From the software workspace:

```tcsh
source ./activate.tcsh
which python3
which yall-run
which condor_submit
which condor_submit_dag
echo 'root-config --version' | "$EIC_SHELL"
python3 "$LFHCAL_REPO/examples/yall/check_shared_conversions.py" -v
```

Stop on a failed check. Graph tests use no raw data, ROOT or scheduler. Read the
[yall-run quick start](https://github.com/paulnord/yall-run/blob/main/docs/QUICKSTART.md)
for the `validate -> plan -> create -> start -> status` lifecycle.

## 2. Small local LFHCal test inside eic-shell

From the host tcsh session:

```tcsh
cd "$LFHCAL_REPO/examples/yall/lfhcal-simple"
source env.tcsh
foreach r (296 298 299 300 303 304)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
$EIC_SHELL
```

Inside `eic-shell` (bash):

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

This converts three pedestal/MIP pairs and extracts their pedestals with a
1000-event limit. It does not attempt MIP calibration or waveform-summary fits.
Use a site-approved interactive allocation; even bounded work is not permission
to run heavy jobs on a login node. `-j 1` limits local concurrency.

## 3. Small Condor + EIC test

Back on the host, run the no-data EIC-shell example supplied with yall-run:

```tcsh
cd "$YALL_RUN_REPO/examples/eic-shell"
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C" -vv
```

It tests ROOT and Python on worker nodes plus dependency execution, without
processing detector data. Wait for success before a production workflow.

## 4. Scan set 1

```tcsh
cd "$LFHCAL_REPO/examples/yall/scan-set-1"
source env.tcsh
foreach r (296 298 299 300 303 304 307 308 309 310)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
yall-run validate
yall-run plan
```

After checking all ten files, paths and resources:

```tcsh
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C" -vv
```

Results go under `$LFHCAL_WORK/scan-set-1`. Campaign records are under
`$LFHCAL_WORK/campaigns`. The 14 FullSet workflows and HV scan are later, larger
exercises; they are not the installation smoke test.

## Updating and restarting

A campaign uses the existing `NewStructure/build` executables. These examples
contain no build jobs. Rebuild only after analysis code, build configuration,
decoder revision or runtime ABI changes; editing a Yallfile does not require a
C++ rebuild. Never update or rebuild a shared checkout while jobs use it.

Re-running the bootstrap does update/build work; use it deliberately, not for
every campaign. In a preview workspace, retain the same explicit fork/branch
overrides when doing so. The updater preserves each checkout's existing origin;
it does not silently replace a fork remote with the upstream remote.

To restart unfinished tasks, first fix the cause and inspect partial outputs,
then use `yall-run resume "$C" --dry-run` followed by `yall-run resume "$C"`.
Do not rerun `start` on an already-started campaign. Resume preserves completed
tasks and restarts unfinished programs from the beginning, not their last event.
Consult the runner's [resume documentation](https://github.com/paulnord/yall-run/blob/main/docs/RESUME.md)
for overwrite and queued-backend restrictions. Changed task resources require a
new campaign with versions that support command-only amendments.
