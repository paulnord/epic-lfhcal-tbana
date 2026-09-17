# Yall examples

These examples show how to run existing LFHCal executables with `yall-run` without adding provenance code to the C++ applications.

`lfhcal-simple`, `scan-set-1`, and `scan-set-2` require **combined named-source
`@each` support**, merged in [yall-run PR #26](https://github.com/paulnord/yall-run/pull/26)
as `a690f2551edb21e099aa2adf4b2b077d12c6a787`. Use current `main` containing
that commit; no feature branch is needed. PR #25 provides named lists/tables
but does not by itself accept two sources after `in`. Do not rely on the
0.9.0 version string: update the runner before validating or creating these
workflows. The Condor workflows additionally use the already-merged
payload-wrapper and `%time` features.

Update both checkouts on the BNL host:

```tcsh
cd ~/eic-2026/yall-run
git switch main
git pull --ff-only

cd ~/eic-2026/epic-lfhcal-tbana
git switch yall-integration
git pull --ff-only

python3 examples/yall/check_shared_conversions.py -v
```

Run these commands in the host Python environment where `yall-run` is
installed. An editable installation follows the checkout; a non-editable
installation must be updated in that same environment. The graph checker
uses temporary test settings and needs no ROOT, raw data, container, or
scheduler. It does not submit jobs or change existing campaigns.

Each of these examples declares its calibration pairs once in `@table pairs`.
A single conversion family visits the ordered union of both columns and
converts each run once. Pedestal fits use unique pedestal values; transfers
wait for their specific pedestal fit and muon conversion. Shared pedestals
are supported without duplicate output owners. Output names remain run-based,
so using multiple pedestal choices for the *same muon run* still requires
separate work areas or explicitly pair-specific output paths.

These refactors rename tasks and remove the introductory `converted` barrier.
Use a **new campaign and fresh work area**, not an amendment to an old campaign.
Existing workers, manifests, products and queued jobs are not modified. No C++
recompilation is required by this Yallfile-only change.

## Where to start

The examples are intentionally arranged from small teaching examples to full production workflows:

* `hgcroc-study/`: one task. The smallest LFHCal example.
* `calibration-pair/`: two dependent tasks.
* `lfhcal-simple/`: the recommended introductory workflow. It converts unique runs from a pedestal/MIP table, fits each pedestal once, and creates calibrations and summaries from the same table.
* `hgcroc-study-condor/`: a small example using the Condor backend.
* `scan-set-1/` and `scan-set-2/`: advanced production examples with a larger DAG and finer-grained dependencies.

Start with `lfhcal-simple` if you want to see Yall fan-out over ordinary lists and correlated pairs without the full TB2026 production machinery.

## TB2026 production workflows

For the TB2026 HGCROC parameter study, production analysis is split by scan set:

* `scan-set-1/Yallfile`: runs 296-310, using `ToAOffsets_TBSPS2026_ParamScan_1.csv`.
* `scan-set-2/Yallfile`: runs 328-361, using `ToAOffsets_TBSPS2026_ParamScan_2.csv`.

Each production Yallfile contains one top-level table of pedestal/MIP pairs. Cross-scan waveform comparisons are intentionally separate downstream work.

These scan-set examples are useful demonstrations of a real analysis, but they are not intended to be the first introduction to Yall syntax.

## Data and work directories

The production examples separate the shared raw-data location from the user's writable analysis area:

```tcsh
setenv LFHCAL_DATA /path/to/TB2026/raw-data
setenv LFHCAL_WORK /path/to/your/yall-work
```

Raw files are then referenced as:

```text
{LFHCAL_DATA}/Run<run>.h2g
```

The production scan-set workflows write products under:

```text
{LFHCAL_WORK}/scan-set-1/
{LFHCAL_WORK}/scan-set-2/
```

Configuration paths and build paths are Yall `@set` values inside each Yallfile.

## Condor environment

Use the same installed `eic-shell` launcher that you use to build LFHCal. Set its path on the **host**, outside the container:

```bash
export EIC_SHELL="$HOME/eic/eic-shell"
```

For tcsh:

```tcsh
setenv EIC_SHELL "$HOME/eic/eic-shell"
```

Before submitting work, verify the launcher's reliable non-interactive interface:

```bash
echo 'root-config --version' | "$EIC_SHELL"
echo 'python3 --version' | "$EIC_SHELL"
```

The current container-side `eic-shell` runs argv-style commands through `bash -c "$@"`, which does not preserve ordinary multi-argument commands. The Condor Yallfiles therefore use the portable `tools/run-in-eic-shell.sh` adapter. It shell-quotes the worker argv and sends one complete command to `eic-shell` on standard input.

The production workflows also set the ROOT/OpenMP thread limits inside the EIC environment to match their one-CPU requests:

```text
@env EIC_SHELL
%wrapper ../../../tools/run-in-eic-shell.sh {EIC_SHELL} \
    /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1
```

Yall archives the adapter and freezes the selected `EIC_SHELL` path and thread-limit arguments. The selected launcher itself must remain visible on the worker nodes and must reference a container runtime, installation, image and bind paths available there. The campaign directory, raw data, work area and LFHCal build must also be visible there. Do not use host-local `/tmp` for a Condor campaign or its products.

Archiving the adapter does not snapshot the container image. Select a fixed image for reproducible work, and use that same environment for compilation and worker execution. A launcher that points to `nightly` still uses a moving image.

Before a large campaign, run the small `examples/eic-shell` smoke example in the yall-run repository to check the launcher on your batch nodes. CERN execution still needs site testing.

## Runtime requests and CERN

The two production scan-set Yallfiles and `hgcroc-study-condor/Yallfile` now set
an explicit campaign default:

```text
%time 2h
```

This requests two hours **per scheduled task job**, including container setup,
not two hours for the entire workflow. It is an initial allocation, not a
measurement or a guarantee that every run finishes within two hours. Adjust it,
or add an indented task/family override, before creating the campaign when a
stage needs a different budget. Run `yall-run validate` and `yall-run plan` on
the host to check parser support and the effective requests before submission.

For Condor this renders `+MaxRuntime = 7200`. CERN uses that site-defined
attribute for runtime policy, including enforcing the maximum, rather than
leaving these tasks at its documented default of 1,200 seconds. This convention
is not CERN-only, but not every Condor pool honors it: without supporting site
policy it is only job metadata and the pool's other limits still apply.

**This does not set HTCondor's separate `allowed_execute_duration` timeout.**
That built-in option places a job on hold when its execution-duration limit is
exceeded; it is neither an alias for `MaxRuntime` nor a way to override a
shorter site limit. No built-in timeout or CERN `JobFlavour` is added by these
examples. See [CERN/LHCb runtime guidance](https://lhcb.github.io/starterkit-lessons/self-guided-lessons/htcondor-more-options.html#resources-and-requirements),
[HTCondor's submit-language documentation](https://htcondor.readthedocs.io/en/latest/man-pages/htcondor-jdl.html),
and the resource documentation in [yall-run PR #19](https://github.com/paulnord/yall-run/pull/19).

**Pulling this update does not change existing campaigns or queued jobs.**
Their resource requests and rendered submit files were frozen at creation;
`yall-run resume` reuses those requests. Create a new campaign to use the new
time budget, choosing a fresh `LFHCAL_WORK` to protect earlier products. Do not
assume resuming an old campaign gives it the new two-hour limit.

## Inspect and run

Build LFHCal in `NewStructure/build` inside `eic-shell`. Run local examples inside that environment; create and submit Condor campaigns from the **host shell**.

Enter an example directory, then:

```tcsh
yall-run validate
yall-run plan
```

To create a frozen campaign:

```tcsh
yall-run create
```

For production campaign records in the writable work area:

```tcsh
mkdir -p $LFHCAL_WORK/campaigns
yall-run create --campaigns-dir $LFHCAL_WORK/campaigns
```

Start the exact campaign directory printed by `create`. In bash, the complete creation/submission sequence is:

```bash
CAMPAIGN=$(yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns") &&
yall-run start "$CAMPAIGN" &&
yall-run status "$CAMPAIGN"
```

Use a fresh `LFHCAL_WORK` for a new production run. A new campaign ID does not change the output paths; existing declared outputs are protected by default.

No LFHCal-specific provenance is embedded into ROOT files; yall-run keeps campaign, task, executable, input/output, scheduler, and attempt provenance in its campaign records.
