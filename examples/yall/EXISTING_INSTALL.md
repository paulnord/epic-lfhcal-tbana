# Existing LFHCal installation

Already installed LFHCal using Fredi's instructions? Keep that installation.
You only need to add **yall-run**, fetch the integration examples, set paths,
and test.

## 1. Install yall-run

Run in the normal host **tcsh** shell:

```tcsh
setenv YALL_RUN_REPO "$HOME/yall-run"
git clone --branch main https://github.com/paulnord/yall-run.git "$YALL_RUN_REPO"
python3 -m pip install --user -e "$YALL_RUN_REPO"

setenv PATH "`python3 -m site --user-base`/bin:$PATH"
rehash

which yall-run
yall-run --version
```

If yall-run is already installed, use the existing checkout instead of cloning
it again.

## 2. Get the LFHCal integration examples

Change directory to your existing LFHCal Git repository, the one containing
`NewStructure/`:

```tcsh
setenv LFHCAL_REPO "`git rev-parse --show-toplevel`"
cd "$LFHCAL_REPO"

git fetch https://github.com/paulnord/epic-lfhcal-tbana.git yall-integration-upstream
git switch --no-track -c yall-integration-upstream FETCH_HEAD
```

If that local branch already exists:

```tcsh
git switch yall-integration-upstream
git pull --ff-only https://github.com/paulnord/epic-lfhcal-tbana.git yall-integration-upstream
```

Do not switch or update a checkout being used by running jobs.

## 3. Set paths

Use your existing LFHCal build and runtime environment. The shared BNL raw data
are currently:

```text
/gpfs01/star/pwg/pnord/eic/2026TBdata/raw
```

In host tcsh:

```tcsh
setenv LFHCAL_DATA "/gpfs01/star/pwg/pnord/eic/2026TBdata/raw"
setenv LFHCAL_WORK "/gpfs01/star/scratch/`id -un`/lfhcal"
setenv EIC_SHELL /path/to/your/eic-shell
mkdir -p "$LFHCAL_WORK/campaigns"
```

If your LFHCal executables are not under `NewStructure/build`, edit the
example's `@set BUILD` to point at the build you already use. Do not rebuild
merely to satisfy the example path.

## 4. Start with the small test

Run `lfhcal-simple` in the same ROOT/LFHCal environment you normally use.
Then try the small Condor/EIC test, and only after that move to `scan-set-1`.

See [SETUP.md](SETUP.md) for the complete test sequence.
