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

Use a checkout containing these examples and a matching LFHCal build at
`NewStructure/build`. Build once in the environment that will execute the
scientific payload. Do not replace or rebuild a checkout used by running jobs.
A change to workflow text alone needs no C++ rebuild; changing the upstream
analysis version or ROOT/decoder ABI can require one.

Install a compatible yall-run on the **submission host**. Python 3.8 or newer is
required. The larger recipes now require **yall-run 0.12.0a7** with the
`%account-provenance` directive from PR #45 (merged as
`5a39498d023b1c9edcaa08926c80f2bb848efda9`). That revision also includes the
partial `@each` binding required by the FullSet recipes. The existing
source checkout install is:

```text
python3 -m pip install --user -e /path/to/yall-run
```

Use the installed command's `--version` and record the actual checkout commit;
an alpha version string alone does not identify supported recipe syntax. The
[graph checks](#validation) fail before any job is submitted if expansion is
incompatible. The bootstrap is an optional alternative that installs and builds
software; it is not a dependency of the workflows.

For a container-wrapped batch example, set the following in your **host tcsh**
session, substituting your existing paths:

```tcsh
setenv LFHCAL_REPO /path/to/epic-lfhcal-tbana
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
