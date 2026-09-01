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

## HTCondor

Run Condor submission on a submit host where `condor_submit` is available, not
from inside the EIC analysis container. The same job file can be submitted with:

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

The supplied `tools/run-in-eic-container.sh` selects Apptainer or Singularity
and preserves the payload argument vector exactly. The Condor wrapper is copied
into the campaign before submission, hashed, and used from that archived
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
