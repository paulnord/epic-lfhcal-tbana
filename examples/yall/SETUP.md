# BNL setup: local LFHCal test, Condor test, then scan-set-1

Use your normal BNL tcsh login/submit session for installation and all Condor work. The one exception is the first local LFHCal test: `lfhcal-simple` is intentionally wrapper-free and is run interactively inside `eic-shell`.

## Install

Create your software workspace in a location visible to batch nodes:

```tcsh
mkdir my_eic_work_with_LFHCAL
cd my_eic_work_with_LFHCAL
curl -fsSL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration/tools/bootstrap-yall-integration.sh | bash
```

The current folder is the install root. The installer installs `eic-shell`, clones/updates `yall-run` on `main` and LFHCal on `yall-integration`, initializes the decoder submodule, and compiles `NewStructure` inside the EIC environment.

Yall is installed editably for both the host Python and the Python inside `eic-shell`. That lets the local LFHCal example run Yall directly inside the EIC environment, while Condor submission still uses the host installation. There is no virtual environment, Python/Condor installation or pip upgrade.

The normal host-side setup is tcsh:

```text
my_eic_work_with_LFHCAL/
    eic-shell
    yall-run/
    epic-lfhcal-tbana/
    activate.tcsh
    site-env.tcsh
```

`eic-shell` itself is bash. The `lfhcal-simple` example therefore includes one separate `env-eic.sh` file specifically for the interactive EIC shell. It is not a second host setup path.

## Storage: shared input, personal scratch output

New installations default to:

```text
LFHCAL_DATA=/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata
LFHCAL_WORK=/gpfs01/star/scratch/<your-login-name>/lfhcal
```

The login name comes from `id -un`. Setup runs `mkdir -p` on the work tree, including creating `/gpfs01/star/scratch/<your-login-name>` if it does not exist. Example setup creates that example's subdirectory. For the first workflows:

```text
/gpfs01/star/scratch/<your-login-name>/
    lfhcal/
        campaigns/
        lfhcal-simple/
        scan-set-1/
```

Software stays in the chosen workspace. Analysis products and campaign records go to the user's scratch area. Paul's PWG directory is input only. Setup does not write there, create directories there, or change permissions there.

`site-env.tcsh` is the local host-side file to edit for different storage paths. If it is sourced before entering `eic-shell`, those environment values are inherited; otherwise `env-eic.sh` uses the same BNL defaults directly. Do not append an example name to `LFHCAL_WORK`; the Yallfiles add their own subdirectories.

## 1. Preflight checks and Yall quick start

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

Before using the LFHCal workflows, spend a few minutes with the [yall-run Quick start](https://github.com/paulnord/yall-run/blob/main/docs/QUICKSTART.md). It explains the `validate -> plan -> create -> start -> status` lifecycle and the distinction between a reusable Yallfile and a frozen campaign.

## 2. Small local LFHCal test inside eic-shell

Start with [`lfhcal-simple`](./lfhcal-simple/README.md). It uses Yall's local backend and no wrapper. The point is to test the real LFHCal software in the EIC environment before adding Condor.

From the normal BNL tcsh session:

```tcsh
cd "$LFHCAL_REPO/examples/yall/lfhcal-simple"
source env.tcsh
foreach r (296 298 299 300 303 304)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
$EIC_SHELL
```

Now inside `eic-shell` (bash):

```bash
source ./env-eic.sh
which yall-run
yall-run validate
yall-run plan
C=$(yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns" -j4)
yall-run start "$C"
yall-run status "$C"
```

`env-eic.sh` sets the LFHCal/Yall paths, storage paths, EIC Python user-bin PATH, and scratch directories inside the container. This submits no Condor jobs. The three pedestal/MIP pairs are `296/298`, `299/300`, and `303/304`. `Convert`, `DataPrep`, and `HGCROCStudy` are limited to the first 1000 events. Results go under `$LFHCAL_WORK/lfhcal-simple`.

When it succeeds:

```bash
exit
```

returns to the normal BNL tcsh login shell.

## 3. Small Condor + EIC test

Next use Yall's purpose-built [`eic-shell` example](https://github.com/paulnord/yall-run/tree/main/examples/eic-shell). This isolates DAGMan, execution on batch nodes, and the EIC payload wrapper without running test-beam analysis.

```tcsh
cd "$YALL_RUN_REPO/examples/eic-shell"
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

It checks ROOT and Python inside the EIC environment on batch nodes, then runs a final dependency check. Repeat `yall-run status "$C"` to inspect progress. Use `set C = ...`, not `setenv C`, for campaign handles in tcsh.

## 4. Scan set 1

Only after the local LFHCal test and the small Condor test work, move on to the first LFHCal production workflow:

```tcsh
cd "$LFHCAL_REPO/examples/yall/scan-set-1"
source env.tcsh
foreach r (296 298 299 300 303 304 307 308 309 310)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
yall-run validate
yall-run plan
```

Check that all ten files are present and readable. The pedestal/muon pairs are `296/298`, `299/300`, `303/304`, `307/308`, and `309/310`.

Then submit from the normal BNL shell:

```tcsh
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C"
yall-run start "$C"
yall-run status "$C"
```

Results go under `$LFHCAL_WORK/scan-set-1`; campaign records and logs go under `$LFHCAL_WORK/campaigns`. Do not start a second campaign targeting the same output directories. Choose a fresh `LFHCAL_WORK` for a rerun.

The FullSet F1/F2/G1 workflows remain later reproduction exercises, not onboarding tests. `lfhcal-simple` is the recommended first LFHCal workflow.

## Updating

Rerun the installer from the software workspace, or use `bash -s -- --prefix /path/to/workspace` after curl. Existing `site-env.tcsh`, data, and campaigns are preserved. Do not update or rebuild the shared checkout while jobs are using it.

Earlier generated `activate.sh` / `site-env.sh` files are no longer used or regenerated. The `.sh` installer and EIC execution adapter are implementation scripts; `lfhcal-simple/env-eic.sh` is the one user-facing bash setup because `eic-shell` itself is bash.
