# BNL setup: small tests, then scan-set-1

Use your **normal BNL tcsh login/submit session** throughout. Python, Yall and
Condor run on the host; ROOT and the LFHCal executables run through `eic-shell`.
You do not need to enter a Bash session or an interactive container.

## Install

Create your software workspace in a location visible to batch nodes:

```tcsh
mkdir my_eic_work_with_LFHCAL
cd my_eic_work_with_LFHCAL
curl -fsSL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration/tools/bootstrap-yall-integration.sh | bash
```

The current folder is the install root. The installer installs `eic-shell`,
clones/updates `yall-run` on `main` and LFHCal on `yall-integration`, initializes
the decoder submodule, and compiles `NewStructure` inside the EIC environment.
It installs Yall with the provided host Python using `pip install --user -e`.
There is no virtual environment, Python/Condor installation or pip upgrade.

Bash in the one-line installer is just the interpreter for that script. It
returns to the same tcsh prompt. The setup files you source are **tcsh only**:

```text
my_eic_work_with_LFHCAL/
    eic-shell
    yall-run/
    epic-lfhcal-tbana/
    activate.tcsh
    site-env.tcsh
```

The EIC installer may create additional files under this software workspace.
Yall's command is in the Python user-bin directory (usually `~/.local/bin`),
which `activate.tcsh` adds to PATH. Reinstalling from another checkout switches
that user installation to the other checkout.

## Storage: shared input, personal scratch output

New installations default to:

```text
LFHCAL_DATA=/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata
LFHCAL_WORK=/gpfs01/star/scratch/<your-login-name>/lfhcal
```

The login name comes from `id -un`. Setup runs `mkdir -p` on the work tree,
**including creating `/gpfs01/star/scratch/<your-login-name>` if it does not
exist**. Example setup creates that example's subdirectory. For scan-set-1:

```text
/gpfs01/star/scratch/<your-login-name>/
    lfhcal/
        campaigns/
        scan-set-1/
```

Software stays in the chosen workspace. Analysis products and the campaign
records created by the commands below go to your scratch area. Keep a copy of
important final products and campaign records in suitable persistent storage.

Paul's PWG directory is **input only**. The setup does not create directories,
download files, write outputs, or change permissions there. If it is not
readable, setup warns you; ask Paul about access or select another input
location. Creating your scratch directory does not grant access to shared data
or to any additional computing allocation.

`site-env.tcsh` is the one local file to edit for different storage paths.
Existing settings are retained on reinstalls; previously set `LFHCAL_DATA` and
`LFHCAL_WORK` also take precedence over the generated defaults. A failure to
create or write your work directory stops setup rather than falling back to
someone else's directory. Do not append `scan-set-1` to `LFHCAL_WORK` itself:
the Yallfile already adds it.

## 1. Preflight checks

After installation, from the software workspace:

```tcsh
source ./activate.tcsh
which python3
which yall-run
which condor_submit
which condor_submit_dag
echo 'root-config --version' | "$EIC_SHELL"
python3 "$LFHCAL_REPO/examples/yall/check_shared_conversions.py" -v
```

All should succeed. The graph test uses no raw data and submits nothing.
`activate.tcsh` sets paths and storage variables, not a virtual environment.

Before using the LFHCal workflows, it is worth spending a few minutes with the
[yall-run Quick start](https://github.com/paulnord/yall-run/blob/main/docs/QUICKSTART.md).
It explains the `validate -> plan -> create -> start -> status` lifecycle and
the distinction between a reusable Yallfile and a frozen campaign.

## 2. Small local Yall test: calculate e

The [`e` example](https://github.com/paulnord/yall-run/tree/main/examples/e) is
a good local test because its Yallfile is deliberately `backend local`, needs
only the host Python, and exercises a nontrivial dependency graph: eight
independent exact partial sums followed by a balanced reduction tree and a
final numerical check. It is more useful here than merely printing `hello`.

```tcsh
cd "$YALL_RUN_REPO/examples/e"
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns" -j 4`
echo "$C"
yall-run start "$C"
yall-run status "$C"
cat e-work/e.txt
```

The final value should be approximately `2.718281828459045`. This test does not
use Condor, ROOT, `eic-shell`, or LFHCal data. It establishes that Yall itself,
its local backend, dependencies, campaign records, and host Python are working.

The example protects its declared outputs. If you intentionally rerun this
local smoke test, remove its tiny test output first with `rm -rf e-work`, then
create a new campaign.

The `pi` example is also a useful map/fan-in demonstration, but it declares
Condor as its default backend and uses a deliberately slow numerical series.
The `e` reduction-tree example is the cleaner first local check.

Use **`set C = ...`**, not `setenv C`, for campaign handles in tcsh.

## 3. Small Condor + EIC test, with no test-beam data

Next use Yall's purpose-built
[`eic-shell` example](https://github.com/paulnord/yall-run/tree/main/examples/eic-shell).
It tests the part the local `e` example intentionally does not: DAGMan,
execution on batch nodes, and the EIC payload wrapper.

```tcsh
cd "$YALL_RUN_REPO/examples/eic-shell"
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

It checks ROOT and Python inside the EIC environment on batch nodes, then runs
a final dependency check. Wait for all three tasks to complete before moving
on. Repeat `yall-run status "$C"` to inspect progress. This tests the scheduler
and container path, not the physics calibration, and downloads no test-beam
data.

## 4. Scan set 1

Only after both small Yall tests work, move on to the first LFHCal production
workflow:

```tcsh
cd "$LFHCAL_REPO/examples/yall/scan-set-1"
source env.tcsh
foreach r (296 298 299 300 303 304 307 308 309 310)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
yall-run validate
yall-run plan
```

Check that all ten files are present and readable and that setup, validation
and planning succeeded. The pedestal/muon pairs are `296/298`, `299/300`,
`303/304`, `307/308` and `309/310`. No private download is needed when those
shared files are available.

Then submit:

```tcsh
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

Results go under `$LFHCAL_WORK/scan-set-1`; campaign records and logs go under
`$LFHCAL_WORK/campaigns`. Do not start a second campaign targeting the same
output directories. Choose a fresh `LFHCAL_WORK` for a rerun. A new campaign ID
does not make output paths unique.

FullSet F1/F2 are later reproduction exercises, not the onboarding test. The
older `lfhcal-simple`, `calibration-pair` and `hgcroc-study` recipes are teaching
examples with their own input/local-execution assumptions; they are not used
by this BNL startup sequence.

## Fresh terminal or existing installation

In a fresh terminal, enter an LFHCal example directory and `source env.tcsh`.
It locates and sources the workspace's `activate.tcsh` automatically.
For the generic Yall examples, source the top-level `activate.tcsh` first.

To update, rerun the installer from the software workspace (or use
`bash -s -- --prefix /path/to/workspace` after curl). Do not rebuild or update
shared sources while jobs are using them. Existing `site-env.tcsh`, data and
campaigns are preserved; these new defaults do not move older outputs.

Earlier generated `activate.sh` / `site-env.sh` files are no longer used or
regenerated. They are not automatically deleted, since they may contain local
edits. The repository's duplicate `env.sh` setup wrappers have been removed.
The `.sh` installer and EIC execution adapter remain implementation scripts,
not a second interactive shell for the user.
