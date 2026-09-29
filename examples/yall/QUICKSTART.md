# LFHCal + yall-run quick start

Already installed LFHCal using Fredi's instructions? Keep that installation.
**Install yall-run → get the examples → set paths → test.**
Commands below use the host **tcsh** shell. Stop on errors.

Starting from scratch instead? See [SETUP.md](SETUP.md#install-in-a-new-workspace).

## Existing installation: do not run the bootstrap just to submit

Use your existing LFHCal build and its working ROOT environment. There are
no build tasks in these example graphs. Do not update or rebuild a checkout
while jobs are using it.

### Download and install yall-run

Requires Git, Python 3.8 or newer, pip, and yall-run 0.12.0a7 or newer.
The commands below download and install yall-run:

```tcsh
setenv YALL_RUN_REPO "$HOME/yall-run"
git clone --branch main https://github.com/paulnord/yall-run.git "$YALL_RUN_REPO"
python3 -m pip install --user -e "$YALL_RUN_REPO"
setenv PATH "`python3 -m site --user-base`/bin:$PATH"
rehash
which yall-run
yall-run --version
```

If you already have yall-run, use that checkout instead of cloning again.
Keep the checkout: the editable install uses it. Retain `YALL_RUN_REPO` and
PATH in your normal shell setup. This does not install or rebuild LFHCal.

### Get the integration examples into your existing checkout

In your existing LFHCal Git repository, the one containing `NewStructure/`:

```tcsh
setenv LFHCAL_REPO "`git rev-parse --show-toplevel`"
cd "$LFHCAL_REPO"
git status --short
```

Preserve any local changes before switching branches. The examples are on
Paul's fork; fetch them explicitly regardless of where your `origin` points:

```tcsh
git fetch https://github.com/paulnord/epic-lfhcal-tbana.git yall-integration-upstream
git diff --stat HEAD FETCH_HEAD -- NewStructure OldStructure configs calibrations .gitmodules
```

If that diff lists analysis or configuration changes, review them and ensure
your build matches before running. Adding only the examples needs no rebuild.

For the first checkout of this branch:

```tcsh
git switch --no-track -c yall-integration-upstream FETCH_HEAD
ls examples/yall/lfhcal-simple/Yallfile examples/yall/scan-set-1/Yallfile
```

If the local branch already exists, use these commands instead:

```tcsh
git switch yall-integration-upstream
git pull --ff-only https://github.com/paulnord/epic-lfhcal-tbana.git yall-integration-upstream
```

### Use your existing LFHCal paths

Set your data directory, a fresh writable output directory, and your existing
EIC launcher. `LFHCAL_DATA` must directly contain `Run*.h2g`.
The BNL shared raw-data directory is `/gpfs01/star/pwg/pnord/eic/2026TBdata/raw`.

```tcsh
setenv LFHCAL_DATA /path/to/complete/raw-input
setenv LFHCAL_WORK /path/to/new-output-root
setenv EIC_SHELL /path/to/eic-shell
mkdir -p "$LFHCAL_WORK/campaigns"
```

With these manual settings, do **not** source `env.tcsh`: it loads the optional
bootstrap setup. Software and data paths must work on worker nodes and inside EIC.

The examples use `@set BUILD ../../../NewStructure/build`. If your executables
are elsewhere, change that line in the chosen Yallfile. An in-source build uses
`../../../NewStructure`. Use the runtime environment compatible with that build.

### Test, then submit

Start with the [1,000-event local test](lfhcal-simple/README.md) in your working
LFHCal/ROOT environment. Next, run the [small Condor/EIC test](SETUP.md#3-small-condor--eic-test).
Condor submission belongs on the host, not inside EIC.

Then try the first full scan, from host tcsh:

```tcsh
cd "$LFHCAL_REPO/examples/yall/scan-set-1"
foreach r (296 298 299 300 303 304 307 308 309 310)
    ls -lh "$LFHCAL_DATA/Run${r}.h2g"
end
yall-run validate
yall-run plan
```

Check that the files exist and the plan and resource requests are appropriate.
Only after those checks succeed:

```tcsh
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C" > "$LFHCAL_WORK/campaign-path.txt"
yall-run start "$C"
yall-run status "$C" -vv
```

Results: `$LFHCAL_WORK/scan-set-1`. Logs: `$LFHCAL_WORK/campaigns`.
`create` freezes the recipe; later edits do not change that campaign.
Use a fresh `LFHCAL_WORK` for an independent rerun.

To retry unfinished work, fix the cause and inspect partial outputs first:

```tcsh
yall-run resume "$C" --dry-run
yall-run resume "$C"
```

## Validation

Check the example graphs without ROOT, detector data, or job submission:

```tcsh
python3 "$LFHCAL_REPO/examples/yall/check_shared_conversions.py" -v
```

More detail: [setup](SETUP.md), [workflow catalog](README.md),
[recovery](https://github.com/paulnord/yall-run/blob/main/docs/RESUME.md).
