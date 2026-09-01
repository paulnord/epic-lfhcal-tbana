# `lfhcal-run`: reproducible local and Condor jobs

`lfhcal-run` executes arbitrary commands. It does not interpret `DataPrep`,
`HGCROCStudy`, ROOT macro, Python, or user-defined program options. The basic
rule is:

> If a command can be expressed as an argument list, `lfhcal-run` can run it.

The runner records the command, working directory, selected environment,
host/CPU, git revision and dirty state, timestamps, exit status, and explicitly
declared file lineage. The canonical record is JSON. If PyROOT is available,
it also creates `provenance.root` and embeds the record in explicitly declared
ROOT outputs under `LFHCalProvenance/lfhcal_run`.

## One job

From the repository root:

```console
python3 tools/lfhcal-run -- ./NewStructure/DataPrep --help
```

Everything after `--` belongs to the payload program. Named file roles are
optional and repeatable:

```console
python3 tools/lfhcal-run \
  --input pedestal=/data/rawHGCROC_307.root \
  --input muon=/data/rawHGCROC_308.root \
  --output calibrated=/data/calibrated_307_308.root \
  -- ./NewStructure/DataPrep [DataPrep options ...]
```

The paths declared to the runner do not replace the corresponding program
arguments. They tell the provenance layer what scientific role each file has.

Free-form campaign notes are separate from file lineage and may be repeated:

```console
python3 tools/lfhcal-run \
  --note "Testing a new calibration choice" \
  --note "Use only for comparison" \
  -- ./NewStructure/DataPrep [DataPrep options ...]
```

Notes are stored in the campaign JSON in the order supplied.

## Several local jobs

A job file contains one shell-quoted argument list per line. Blank lines and
comments are ignored:

```text
# A job without explicit file lineage
python3 my_summary.py --run 298

# Per-job metadata precedes --; the payload follows it
--name wave-298 --input data=run298.root --output wave=wave298.root -- ./HGCROCStudy -w -i run298.root -o wave298.root
--name wave-300 --input data=run300.root --output wave=wave300.root -- ./HGCROCStudy -w -i run300.root -o wave300.root
```

Run at most four simultaneously:

```console
python3 tools/lfhcal-run -j 4 jobs.txt
```

Lines are parsed with shell quoting, but are launched directly without a shell.
Pipes, redirection, variable expansion, and compound shell commands therefore
need an explicit shell payload, for example:

```text
bash -lc './analysis input.root > analysis.log 2>&1'
```

## Dependent campaigns

When jobs depend on one another, the same manifest can use a small,
DAGMan-inspired vocabulary. `JOB` defines a named arbitrary command,
`PARENT ... CHILD ...` defines dependencies, and `RETRY` allows additional
execution attempts after failure:

```text
JOB pedestal --output pedestal=ped.root -- ./make-pedestal -o ped.root
JOB muon --output muon=mu.root -- ./make-muon -o mu.root
JOB calibration --input pedestal=ped.root --input muon=mu.root --output calibrated=cal.root -- ./calibrate ped.root mu.root cal.root

PARENT pedestal muon CHILD calibration
RETRY pedestal 2
RETRY muon 2
RETRY calibration 1
```

Job names use letters, digits, `_`, `-`, and `.`, beginning with a letter.
Every job in a dependent campaign must be named, and names must be unique.
Dependency records may appear before or after job records. The runner rejects
unknown job names, self-dependencies, and dependency cycles before execution.

Locally, the runner releases a job only after all its parents succeed, while
still running as many ready jobs as `-j N` permits:

```console
python3 tools/lfhcal-run -j 4 campaign.txt
```

A retry creates another provenance attempt beneath the same intended job.
After a job exhausts its retries, its descendants are marked blocked and are
not executed. Manifests without `PARENT` or a nonzero `RETRY` remain ordinary
flat campaigns and retain the original one-command-per-line behavior.

### TB2026 parameter-scan end-to-end campaign

`tools/make-tb2026-paramscan-dag` turns one pedestal/muon pair into the
established TB2026 Set-1 chain. It generates 12 jobs: workspace preparation,
two parallel raw conversions, pedestal extraction, calibration transfer,
initial muon calibration, MIP selection, three reduced refinement rounds,
application of the `Imp3R` calibration, and waveform analysis.

For the smallest established Set-1 pair, pedestal 296 and muon 298:

```console
python3 tools/make-tb2026-paramscan-dag \
  --pedestal-run 296 \
  --muon-run 298 \
  --raw-dir /path/to/2026TBdata \
  --output-dir /path/to/full-chain-296-298 \
  --manifest full-chain-296-298.txt \
  --check
```

`--check` verifies both `Run296.h2g` and `Run298.h2g`, the three built
executables, and all referenced configuration files before writing the
manifest. Use `--force` only when intentionally replacing an existing
manifest. Paths and commands in the generated file are fully expanded, so it
can be inspected directly and submitted without relying on shell variables.

Run the generated campaign locally with `-j 2`, or pass it to the Condor
invocation below. Only the two conversions can overlap in this particular
dependency graph; the calibration stages remain ordered.

### Fetching TB2026 raw files

Fetch individual runs or inclusive ranges from the JLab XRootD store before
generating a campaign:

```console
python3 tools/fetch-tb2026-raw \
  --destination /path/to/2026TBdata \
  137 138-149 153 159 165 178
```

New destinations use a normal `xrdcp`; existing destinations use
`xrdcp --continue`. The dedicated
[`fetch-tb2026-raw` guide](fetch-tb2026-raw.md) documents dry runs, forced
replacement, remote directory listing, and alternate sources.

## HTCondor

Run Condor submission on a submit host where `condor_submit` and, for dependent
campaigns, `condor_submit_dag` are available—not from inside the EIC analysis
container. The same job file can be submitted with:

```console
python3 tools/lfhcal-run --condor jobs.txt
```

The generated Condor worker is what enters the analysis container. A wrapper
passed with `--condor-wrapper` must accept the worker command and its arguments,
then execute that command inside the container:

```text
submit host:  lfhcal-run --condor
execute node: container wrapper -> lfhcal-run worker -> analysis command
```

The initial backend assumes that the repository, campaign directory, data, and
outputs are on a filesystem shared by the submit and execute hosts. For a BNL
container wrapper:

```console
python3 tools/lfhcal-run \
  --condor \
  --condor-wrapper tools/run-in-eic-container.sh \
  --environment-file /path/to/eic-shell \
  --container-image /path/to/local/lib/eic_xl-nightly \
  --request-cpus 1 \
  --request-memory 4GB \
  jobs.txt
```

Site-specific submit entries remain configuration, not analysis knowledge:

```console
python3 tools/lfhcal-run --condor \
  --condor-extra 'requirements=...' \
  --condor-extra '+MyProject="LFHCal"' \
  jobs.txt
```

Use `--dry-run` to inspect the generated submit description without submitting.

For a dependent campaign, the Condor backend compiles the same manifest into
a real DAGMan description, sharing one generated `condor.sub` among the nodes:

```text
JOB lfhcal_0000_pedestal /.../condor.sub
VARS lfhcal_0000_pedestal lfhcal_job_index="0" lfhcal_node="pedestal"
RETRY lfhcal_0000_pedestal 2

JOB lfhcal_0002_calibration /.../condor.sub
VARS lfhcal_0002_calibration lfhcal_job_index="2" lfhcal_node="calibration"

PARENT lfhcal_0000_pedestal lfhcal_0001_muon CHILD lfhcal_0002_calibration
```

It submits that file with `condor_submit_dag`. DAGMan controls release,
failure blocking, and retries; each retry still calls the common provenance
worker and therefore creates a distinct attempt record for the same campaign
job. The generated `lfhcal_...` node names prevent collisions with DAGMan
reserved words such as `PARENT` and `CHILD`; the original job name remains in
`campaign.json`, output filenames, and provenance. Flat campaigns continue to
use `condor_submit` and a single `queue N` submit description.

The supplied `tools/run-in-eic-container.sh` selects Apptainer or Singularity
and preserves the payload argument vector exactly. It also binds standard EIC
host paths that exist on the execute node (`/media`, `/cvmfs`, `/gpfs`,
`/gpfs01`, `/gpfs02`, and `/direct`), matching the paths discovered by the
generated `eic-shell`. Set the comma-separated `LFHCAL_CONTAINER_BINDPATH`
environment variable to replace that automatic list. The Condor wrapper is
copied into the campaign before submission, hashed, and used from that archived
location. `--environment-file` similarly preserves
small environment-defining files such as the generated outer `eic-shell`;
repeat it when more than one file matters. A wrapped worker invokes `python3`
through the container's `PATH`, so the provenance runner uses the EIC Python
rather than a host `/usr/bin/python3` path carried into the container.

`--container-image` records the requested image path, its symlink target, its
fully resolved path, and the content digest encoded by a CVMFS `.images`
target. The multi-gigabyte image is deliberately not duplicated into every
campaign. For example, a mutable `eic_xl:nightly` name may resolve to an
immutable path like `.images/sha256:50/725b...`; the reconstructed
`sha256:50725b...` identity is what makes the execution environment precise.
The resolved path is exported to the wrapper as `LFHCAL_CONTAINER_IMAGE`,
pinning the intended image even if the `nightly` alias advances while a job is
waiting in the queue.
Execution attempts also discover this information automatically from
`APPTAINER_CONTAINER` or `SINGULARITY_CONTAINER` inside a container.

## Provenance layout

By default each invocation creates:

```text
lfhcal-runs/campaign-.../
  campaign.json
  environment/
    condor-wrapper.sh        # exact submitted wrapper, when configured
    files/
      000-eic-shell          # explicitly archived environment files
  campaign.dag               # generated for a dependent Condor campaign
  condor.sub                 # generated Condor node description
  jobs/
    0000-job-name/
      latest.json
      attempts/
        attempt-.../
          provenance.json
          provenance.root       # when PyROOT is available
          stdout.log
          stderr.log
```

Each execution attempt gets its own directory. A Condor retry therefore remains
a new attempt of the same intended campaign job rather than becoming a new
scientific job.

Only a conservative allowlist of environment variables is recorded. In
particular, the runner does not dump the complete environment, which may contain
credentials or unrelated secrets.
