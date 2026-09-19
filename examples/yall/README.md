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
`ToAOffsets_TBSPS2026_ParamScan_2.csv`.

The repository has reproduction examples for all 14 published TB2026 FullSet
B-G merged-muon calibrations:

| Workflow | Pedestal | Muon runs in Fredi's merge order | Published set |
| --- | ---: | --- | --- |
| `fullset-b1-repro` | 071 | 072–084 | `FullSetB_1` |
| `fullset-b2-repro` | 126 | 127–133 | `FullSetB_2` |
| `fullset-c1-repro` | 137 | 147,148,149,146,145,144,141,142,143,140,139,138 | `FullSetC_1` |
| `fullset-c2-repro` | 188 | 189,194,190,191,193,192 | `FullSetC_2` |
| `fullset-c3-repro` | 278 | 289–293 | `FullSetC_3` |
| `fullset-d1-repro` | 206 | 208–224 | `FullSetD_1` |
| `fullset-d2-repro` | 264 | 266–270 | `FullSetD_2` |
| `fullset-e1-repro` | 372 | 373–378 | `FullSetE_1` |
| `fullset-e2-repro` | 420 | 421,422,423,425,424 | `FullSetE_2` |
| `fullset-e3-repro` | 471 | 473,474,477,478,481,482 | `FullSetE_3` |
| `fullset-f1-repro` | 431 | 426–430 | `FullSetF_1` |
| `fullset-f2-repro` | 471 | 472,475,476,479,480,483 | `FullSetF_2` |
| `fullset-g1-repro` | 485 | 484,486–491 | `FullSetG_1` |
| `fullset-g2-repro` | 529 | 530–537 | `FullSetG_2` |

Each FullSet workflow has one typed `@table runs type run:` table. A single
`convert-{type}-{run}` family converts every row. `merge-muon` binds
`type=muon`; the `{type}-{run}` pedestal family binds only
`type=pedestal` and inherits its run from the compatible parent.

FullSet B-F use the V2 summing-board mapping and shared FullSetA-F bad-channel
map. FullSet G uses V1 and the FullSetG bad-channel map. The examples preserve
Fredi's ToA selections, including FullSetC_2 offsets for C3 and FullSetF
offsets for E3.

The B-E examples include `download_raw.tcsh`, which downloads exactly the
pedestal and merged-muon inputs from the JLab XRootD source. All published
FullSet results can be compared with:

```tcsh
python3 "$LFHCAL_REPO/examples/yall/compare_fullset.py" --set-name FullSetC_2
```

The comparison tool reports refinement-stage differences and assembles plot
PDFs using `pdfunite`, `qpdf`, or Ghostscript.

The production Yallfiles read `Run<run>.h2g` from `LFHCAL_DATA` and write
under `LFHCAL_WORK/<example-name>`. Source `env.tcsh` from the example
directory to load the bootstrapped installation and prepare the work area.

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
`a690f2551edb21e099aa2adf4b2b077d12c6a787`). The FullSet workflows also
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
shared pedestal runs do not produce duplicate output owners. It also checks all 14 published FullSet task counts, typed conversion
families, muon-only merge fan-in, inherited pedestal runs, and transfer
dependencies that follow the run table. Reusing the same muon run with different pedestal choices still requires
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
