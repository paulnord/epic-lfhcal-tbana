# BNL setup: local LFHCal test, Condor test, then scan-set-1

**[TL;DR — the commands to install and run the small tests](SETUP_TLDR.md)**  
Add yall-run → get the integration examples → set paths → test.

**Already installed LFHCal using Fredi's instructions? Start below.** Keep your
working installation. The optional [new-workspace installer](#install-in-a-new-workspace)
is for a fresh installation, not a prerequisite for using these examples.

Use the normal BNL tcsh login/submit session for installation and Condor work.
The small `lfhcal-simple` test is deliberately wrapper-free: run it in your
working LFHCal/ROOT environment. The fresh-installation route below uses
`eic-shell` (bash). Do not submit Condor jobs from inside the container.
Yall is optional; it does not replace the analysis software or change its fitter.

## Add yall-run to an existing LFHCal installation

### 1. Download and install yall-run

Having LFHCal installed does not mean yall-run is installed. In host tcsh,
with Git and Python 3.8 or newer plus pip available:

```tcsh
setenv YALL_RUN_REPO "$HOME/yall-run"
git clone --branch main https://github.com/paulnord/yall-run.git "$YALL_RUN_REPO"
python3 -m pip install --user -e "$YALL_RUN_REPO"
setenv PATH "`python3 -m site --user-base`/bin:$PATH"
rehash
which yall-run
yall-run --version
```

Stop on errors. If you already have yall-run, keep its existing checkout and
skip cloning/installing it again. `$HOME/yall-run` is an example destination,
not a required sibling of LFHCal. Keep it in place because `-e` uses that source
checkout. Retain the PATH setting in your normal shell setup after it works.
If your Python disallows `--user`, use a site-supported Python environment;
do not use sudo or bypass package-management protections.

### 2. Fetch and switch to the LFHCal integration branch

**Before upstream PR #82 is merged, an upstream LFHCal checkout does not have
these examples.** Installing yall-run or setting `LFHCAL_REPO` will not add them.

Change directory to your existing LFHCal Git repository, the one containing
`NewStructure/`, then run:

```tcsh
setenv LFHCAL_REPO "`git rev-parse --show-toplevel`"
cd "$LFHCAL_REPO"
git status --short
```

Stop if you are in the wrong repository or have local changes to preserve.
Do not switch or update a checkout used by running jobs. Fetch from Paul's fork
explicitly, without assuming that your `origin` points there:

```tcsh
git fetch https://github.com/paulnord/epic-lfhcal-tbana.git yall-integration-upstream
git diff --stat HEAD FETCH_HEAD -- NewStructure OldStructure configs calibrations .gitmodules
```

Stop if fetch fails. A nonempty diff means the review branch also differs from
your installed analysis/configuration version; review it and ensure your build
matches before running. Adding only workflow files requires no C++ rebuild,
but switching to different analysis sources does not update existing binaries.

For the first checkout of this local review branch:

```tcsh
git switch --no-track -c yall-integration-upstream FETCH_HEAD
ls examples/yall/lfhcal-simple/Yallfile examples/yall/scan-set-1/Yallfile
```

If that local branch already exists, use `git switch yall-integration-upstream`
instead of `switch -c`; after the switch succeeds, update it with:

```tcsh
git pull --ff-only https://github.com/paulnord/epic-lfhcal-tbana.git yall-integration-upstream
```

Do not pull this branch into an unrelated current branch. Stop on errors or a
refused fast-forward; do not reset or force an update. These commands leave
`origin` and your original branch in place. After PR #82 is merged, update
upstream `main` through your usual upstream remote instead.

### 3. Set paths and use the existing build

Continue with [Use your existing LFHCal paths](QUICKSTART.md#use-your-existing-lfhcal-paths)
now that the example files actually exist. `LFHCAL_DATA` must directly contain
`Run*.h2g`; the BNL shared location is `/gpfs01/star/pwg/pnord/eic/2026TBdata/raw`.
Choose your own writable `LFHCAL_WORK`. For EIC-wrapped batch workflows,
`EIC_SHELL` must point to your working launcher.

The examples default to `../../../NewStructure/build`. If your executables are
elsewhere, change the example's `@set BUILD` to that existing build directory;
an in-source build uses `../../../NewStructure`. Do not rebuild just to satisfy
a directory convention. Run the bounded [lfhcal-simple](lfhcal-simple/README.md)
test in the same runtime environment as the existing build before a full scan.

**Do not source bootstrap-generated activation files for an unrelated existing
installation.** The `env.tcsh` and `lfhcal-simple/env-eic.sh` conveniences assume
the new-workspace layout. The detailed [existing-installation guide](QUICKSTART.md#existing-installation-do-not-run-the-bootstrap-just-to-submit)
explains the manual route. The rest of this page describes the optional fresh
BNL installation and its tests; it is not a second installation to perform.

## Install in a new workspace

The installer creates/updates checkouts and builds LFHCal. It is not the command
to use merely to start another campaign. Use a new workspace for this preview,
not a checkout used by running jobs. Commands below download the installer to a
file so it can be inspected before execution.

The two installation blocks below are alternatives. The directory names are
examples of a parent workspace, not required names; do not run both blocks.
If this installer has already completed in your chosen workspace, continue
with the preflight checks rather than rerunning it.

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

The larger Yallfiles require yall-run **0.12.0a7** with PR #45 or newer.
They explicitly set `%account-provenance off`; set it to `full` only when
operator attribution is needed and permitted by your site's privacy policy.
This does not anonymize paths or logs. See [account provenance](README.md#account-provenance).

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
