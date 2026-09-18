# LFHCal Yall examples

**New BNL user: start with [SETUP.md](SETUP.md).** It installs in your chosen
software workspace, uses shared PWG raw input and your own scratch work area,
and walks through small host/container tests, the three-task EIC Condor smoke
test, and then `scan-set-1`. All interactive commands use your normal tcsh
login/submit session. FullSet F2 is not the first test.

## Production workflows

`scan-set-1` covers pedestal/muon pairs `296/298`, `299/300`, `303/304`,
`307/308`, `309/310`, using `ToAOffsets_TBSPS2026_ParamScan_1.csv`.
`scan-set-2` covers the later parameter scan, using
`ToAOffsets_TBSPS2026_ParamScan_2.csv`. Cross-scan waveform comparisons are
separate downstream work.

`fullset-f1-repro`, `fullset-f2-repro`, and `fullset-g1-repro` reproduce the
merged FullSet F and G muon calibration recipes. They are larger, later
validation exercises.

Each FullSet workflow declares its scientific run configuration once in a
typed `@table runs type run:` table:

| Workflow | Pedestal row | Muon rows | Expanded pedestal task | Tasks |
| --- | ---: | --- | --- | ---: |
| `fullset-f1-repro` | 431 | 426–430 | `pedestal-431` | 18 |
| `fullset-f2-repro` | 471 | 472, 475, 476, 479, 480, 483 | `pedestal-471` | 19 |
| `fullset-g1-repro` | 485 | 484, 486–491 | `pedestal-485` | 20 |

One `convert-{type}-{run}` family converts all rows. `merge-muon` binds
`type=muon`, so its parent fan-in and `@input.parts` contain only compatible
muon rows. The `{type}-{run}` pedestal family uses `@each type pedestal` to
bind only `type`; it inherits the unresolved `run` from its compatible
conversion parent. The transfer task names that patterned pedestal family as a
parent, rather than hard-coding a run, so conversion, pedestal extraction, and
the transfer dependency all follow a table change together.

The production Yallfiles read `Run<run>.h2g` from `LFHCAL_DATA`, and write under
`LFHCAL_WORK/<example-name>`. Source `env.tcsh` from the example directory to
load the installation and prepare your work directory. Input data are not
created, modified or downloaded by setup. See [SETUP.md](SETUP.md) for the BNL
defaults and the `--campaigns-dir` commands that keep campaign records in your
own scratch area too.

## Teaching examples

`hgcroc-study` is a one-task local example. `calibration-pair` demonstrates two
calibration tasks using pre-existing ROOT inputs. `lfhcal-simple` is the bounded
local smoke test: it converts three pedestal/MIP pairs and extracts the three
pedestals with a 1000-event limit. It deliberately stops before MIP scaling and
waveform-summary work because the bounded sample is not intended to populate
those fits and histograms reliably. The pair table is retained so the smoke test
still exercises shared conversion and dependency expansion.

The `calibration-pair`, `hgcroc-study`, and `hgcroc-study-condor` directories each
contain a README describing the input file that must be supplied. They do not
ship example ROOT data. The notes use TB2026 runs `296/298` as an example
pedestal/MIP pair and run `298` as an example HGCROC study input; those run
numbers are examples rather than hard requirements.

These older local recipes have their own input assumptions and do not
automatically acquire a container wrapper or switch to scratch output just by
sourcing an environment file. Do not run them as heavy work on a login node.
`hgcroc-study-condor` is a small batch example with a pre-existing converted
input. For a fresh BNL installation, use the no-data EIC/Condor test in SETUP.md
instead.

## Runner version and graph checks

`lfhcal-simple` and the scan workflows require combined named-source `@each`
support from yall-run PR #26 (commit
`a690f2551edb21e099aa2adf4b2b077d12c6a787`). The three FullSet workflows also
require partial explicit binding and patterned-parent inheritance from yall-run
PR #33, merged as commit
`1081e9dd39418262588248272618130ce0503b8a`. Use `main` containing that commit,
not just a matching version string. The Condor workflows also use the merged
payload-wrapper and `%time` features.

```tcsh
python3 "$LFHCAL_REPO/examples/yall/check_shared_conversions.py" -v
```

This checks graph expansion without ROOT, raw data or scheduler submission.
Conversions visit the ordered union of pedestal and muon columns once each;
shared pedestal runs do not produce duplicate output owners. It also checks
the three FullSet task counts, typed conversion families, muon-only merge
fan-in, inherited pedestal runs, and transfer dependencies that follow the run
table. Reusing the same muon run with different pedestal choices still requires
separate work areas or explicitly pair-specific output paths.

## Execution boundary

Yall and Condor run on the host. Production scientific commands use the
`tools/run-in-eic-shell.sh` adapter, which sends a quoted command through
`eic-shell` standard input and preserves argument/exit-status behavior.
The `.sh` suffix identifies its interpreter, not an interactive shell you
need to enter. Do not submit Condor campaigns from inside the container.

The scan workflows request one CPU and set `ROOT_MAX_THREADS=1` and
`OMP_NUM_THREADS=1` inside the payload environment. The adapter is archived by
Yall; its external EIC launcher and container image are not automatically
archived or pinned. Use the same EIC environment to compile and execute LFHCal.
A launcher pointing at `nightly` still selects a moving image.

Software, inputs, outputs and campaign records must be visible on batch nodes,
including through the relevant container binds. Host readability alone does
not establish container readability; that is why the batch smoke test comes
before an analysis.

## Runtime and existing campaigns

`%time 2h` is a per-task request, including container startup, not a campaign
runtime estimate. Condor renders it as `+MaxRuntime = 7200`. Enforcement depends
on site policy; it is not the separate `allowed_execute_duration` setting.
Do not assume BNL enforces CERN's runtime policy.

Pulling code or editing a Yallfile does not update already-created campaigns or
queued jobs. `resume` reuses frozen requests. Use new campaigns and fresh output
roots for changed recipes or resource requests, and do not rebuild the shared
LFHCal checkout while jobs are using it.

Yall records campaign, task, executable, input/output, scheduler and attempt
provenance separately; it does not inject LFHCal-specific provenance into ROOT
files. Preserve campaign records together with important final products.
