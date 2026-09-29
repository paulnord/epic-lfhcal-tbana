# Optional yall-run workflows for LFHCal

These examples launch the existing LFHCal programs locally or through HTCondor.
They do not replace the programs, choose a new fitter, or modify the normal
CMake build. The yall-run package is a separate optional dependency.

## What is in this contribution?

The review branch `paulnord/epic-lfhcal-tbana:yall-integration-upstream` starts at
upstream `eic/epic-lfhcal-tbana:main` commit
`36715943c68566f6758982bf3530a1eb1f072607`. It imports `examples/` and `tools/`
from the existing `yall-integration` branch at
`0f82db064638b7a2abd595fbd02173fa84e8ebdc`, with setup/documentation updates.
The original development branch is retained rather than rewritten.

There are no changes to `NewStructure`, `OldStructure`, detector configurations,
published calibrations, the decoder gitlink or the build system. Adaptive fits,
FFT benchmarks, full-chain comparison launchers and timeout-recovery campaigns
are separate work and are not included here. Any scientific-code changes already
in the upstream base are not changes introduced by this contribution.

## Choose the starting point

| Situation | Start here |
| --- | --- |
| New BNL user, normal tcsh submit shell | [BNL setup](SETUP.md) |
| Already have a working LFHCal build and EIC launcher | Existing-installation procedure below |
| Learn a single local task | [hgcroc-study](hgcroc-study/README.md); requires a converted ROOT input |
| Bounded first detector-data test | [lfhcal-simple](lfhcal-simple/README.md); 1000-event conversion/pedestal test |
| First full LFHCal batch workflow | [scan-set-1](scan-set-1/README.md) |
| FullSet B-G or HV-scan reproduction | [Workflow catalog](README.md) |

The examples do not distribute the raw detector data. Input permissions and
complete transfers must be arranged independently. The BNL PWG and scratch paths
in the setup guide are site-specific defaults, not portable requirements.

## Existing installation: do not run the bootstrap just to submit

Already running LFHCal after following Fredi's instructions? Keep that
installation and its working analysis environment. You are adding a launcher,
not replacing your LFHCal setup. Having LFHCal installed does **not** mean you
already have yall-run or the new LFHCal examples: obtain both below.

The examples currently expect matching LFHCal executables at
`NewStructure/build`. If your build is elsewhere (including an in-source build
in `NewStructure`), change the example's `@set BUILD` to that existing build
directory before `validate` and `create`; do not rebuild merely to satisfy a
path convention. Use the runtime environment compatible with that build.
Do not switch, update, or rebuild a checkout used by running jobs.

### Download and install yall-run

For a collaborator who does not yet have yall-run, run the following in the
normal **host tcsh** session, not inside eic-shell. Git and Python 3.8 or newer
with pip must already be available. Stop if cloning or installation fails.

```tcsh
setenv YALL_RUN_REPO "$HOME/yall-run"
git clone --branch main https://github.com/paulnord/yall-run.git "$YALL_RUN_REPO"
python3 -m pip install --user -e "$YALL_RUN_REPO"

setenv PATH "`python3 -m site --user-base`/bin:$PATH"
rehash

which yall-run
yall-run --version
git -C "$YALL_RUN_REPO" rev-parse HEAD
```

`$HOME/yall-run` is the actual source directory created by `git clone`, not a
placeholder or a required workspace layout. Choose another location in the
first line if desired; it need not be alongside LFHCal. For queued workflows,
use a location accessible from the worker nodes. If you already have a yall-run
checkout, set `YALL_RUN_REPO` to that directory and skip `git clone`; do not
clone over it or update it while an active local campaign is using it.

The install is for your host Python account and does not require administrator
privileges. `-e` makes the installed command use this source checkout, so keep
the checkout in place. The PATH line makes the installed command visible in
this shell. After these checks succeed, retain `YALL_RUN_REPO` and the PATH
setting in your normal tcsh login setup (for example, `~/.tcshrc`); do not
repeat the clone and install at every login. These commands do not edit your
shell startup files automatically. If your Python installation disallows
`--user`, use a site-supported Python environment rather than adding `sudo`
or bypassing its package-management protections.

This installs **yall-run only**. It does not clone, rebuild, move, or reconfigure
LFHCal, install ROOT or Condor, or require bootstrap-generated activation files.

The larger recipes require **yall-run 0.12.0a7** with the
`%account-provenance` directive from PR #45 (merged as
`5a39498d023b1c9edcaa08926c80f2bb848efda9`). That revision also includes the
partial `@each` binding required by the FullSet recipes. The commands
above clone `main`; record the printed commit as well as the version, since an
alpha version string alone does not identify supported recipe syntax. The
[graph checks](#validation) fail before any job is submitted if expansion is
incompatible. The bootstrap is an optional alternative for a fresh installation,
not a dependency of these workflows.

### Get the integration examples into your existing checkout

Before upstream PR #82 is merged, the examples are on **Paul's fork**, on
`yall-integration-upstream`. Pulling upstream `main` or installing yall-run
alone does not add these files to LFHCal.

First change directory to your **existing LFHCal source repository** (the Git
checkout containing `NewStructure/`, not the yall-run checkout or a scratch
analysis directory). Then, in host tcsh:

```tcsh
setenv LFHCAL_REPO "`git rev-parse --show-toplevel`"
cd "$LFHCAL_REPO"
git status --short
```

Stop if this is not the LFHCal repository or if local changes are listed;
preserve your changes before switching. Do not proceed while jobs use this
checkout. Fetch explicitly from the fork, independently of where `origin` points:

```tcsh
git fetch https://github.com/paulnord/epic-lfhcal-tbana.git yall-integration-upstream
git diff --stat HEAD FETCH_HEAD -- NewStructure OldStructure configs calibrations .gitmodules
```

Stop if fetch fails. If the diff is nonempty, the review branch also differs
from your installed analysis/configuration version. Review that difference and
ensure a matching build before running analysis; a branch switch does not
update an old executable. The integration itself changes no C++ relative to
its upstream base, so adding only the examples does not require a rebuild.

For the **first checkout of this branch**:

```tcsh
git switch --no-track -c yall-integration-upstream FETCH_HEAD
ls examples/yall/lfhcal-simple/Yallfile examples/yall/scan-set-1/Yallfile
```

Stop on any error. This creates a local review branch without merging into
your original branch, changing `origin`, or creating a new installation.
Do not use `git pull origin yall-integration-upstream` while on another branch:
that remote may not have it, and pull integrates into the current branch rather
than switching branches.

**Already checked out this local review branch?** Use `git switch
yall-integration-upstream` instead of `switch -c`. Only after the switch succeeds,
update it with:

```tcsh
git pull --ff-only https://github.com/paulnord/epic-lfhcal-tbana.git yall-integration-upstream
```

If fast-forwarding is refused, stop rather than reset or force an update.
After PR #82 is merged, users of upstream `main` can update that branch through
their usual upstream remote instead. Existing campaigns remain unchanged.

### Use your existing LFHCal paths

`LFHCAL_REPO` now names the checkout selected above, with the examples present.
For a container-wrapped batch example, set the remaining variables in your
**host tcsh** session, substituting your existing paths. `LFHCAL_DATA` must
directly contain `Run*.h2g`; the shared BNL location is
`/gpfs01/star/pwg/pnord/eic/2026TBdata/raw`.

```tcsh
setenv LFHCAL_DATA /path/to/complete/raw-input
setenv LFHCAL_WORK /path/to/new-output-root
setenv EIC_SHELL /path/to/eic-shell
mkdir -p "$LFHCAL_WORK/campaigns"
cd "$LFHCAL_REPO/examples/yall/scan-set-1"
yall-run validate
yall-run plan
```

With those variables already set, do **not** source `env.tcsh`: that convenience
file loads a bootstrap-generated workspace and may replace manual settings.
The Yallfiles use your variables directly. In bash, use `export NAME=value`
instead of `setenv`; the example recipes themselves are unchanged.

Before continuing, check that every listed raw file exists, all paths are visible
on batch nodes and inside the container, and the requested memory/time are
appropriate. In particular, a large merged FullSet can need more than the
example's two-hour request; D1 is not a quick smoke test. Change resources before
creating the campaign rather than expecting a frozen campaign to adopt edits.

Submit only after validation and plan inspection succeed:

```tcsh
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
echo "$C" > "$LFHCAL_WORK/campaign-path.txt"
yall-run start "$C"
yall-run status "$C" -vv
```

`create` freezes a campaign. `start` submits that exact campaign. A successful
submission is not a completed analysis; check the status and outputs. There are
no build tasks in these example graphs. Each task uses the existing executables.
Use a different `LFHCAL_WORK` for an independent rerun because the Yallfiles add
fixed example subdirectories below it.

## Execution and recovery boundaries

Yall and Condor stay on the host. `tools/run-in-eic-shell.sh` sends only scientific
payload commands into EIC. Local wrapper-free teaching recipes must instead run
where ROOT and their input files are available; their READMEs state the specific
assumptions. No heavy work should be run on a login node merely because the
backend is named `local`.

The wrapper is archived with a campaign, but an external EIC launcher or image
is not automatically made immutable. Record/pin the environment for comparisons;
a launcher selecting `nightly` is not a fixed image. The analysis and decoder
source revision, binary/library versions, data inputs and output path all matter.

To recover an interrupted campaign, fix the original cause and inspect partial
products, then use `yall-run resume "$C" --dry-run` and `yall-run resume "$C"`.
The runner preserves completed tasks. It restarts unfinished executables from
the beginning; it is not an event-level checkpoint. Check the
[resume](https://github.com/paulnord/yall-run/blob/main/docs/RESUME.md) and
[amendment](https://github.com/paulnord/yall-run/blob/main/docs/AMENDMENTS.md)
documentation for the installed version. Do not overwrite a frozen campaign or
silently delete partial results. Do not rebuild just to retry a job whose only
problem was a time allowance or unavailable input.

## Validation

From the LFHCal repository root, with a compatible yall-run importable:

```text
python3 -m unittest discover -s tools/tests -v
python3 examples/yall/check_shared_conversions.py -v
bash -n tools/bootstrap-yall-integration.sh
bash -n tools/run-in-eic-shell.sh
```

These checks validate environment setup and graph expansion without ROOT, raw
data or scheduler submission. Tests that execute real tcsh skip when tcsh is not
installed. Graph checks cover the small test, both parameter scans, all 14
FullSets and the HV scan, including shared pedestal dependencies and conflicting
output ownership. They do not establish detector-calibration correctness.

The GitHub Actions workflow performs these offline checks against pinned yall-run
revisions. A fresh site smoke test on the rebased LFHCal version is still required
before treating it as an end-to-end validated release. Historical comparison
notes in individual example directories describe their original runs, not a
promise that the current upstream analysis reproduces every value exactly.
