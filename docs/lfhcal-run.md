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
./tools/lfhcal-run -- ./NewStructure/DataPrep --help
```

Everything after `--` belongs to the payload program. Named file roles are
optional and repeatable:

```console
./tools/lfhcal-run \
  --input pedestal=/data/rawHGCROC_307.root \
  --input muon=/data/rawHGCROC_308.root \
  --output calibrated=/data/calibrated_307_308.root \
  -- ./NewStructure/DataPrep [DataPrep options ...]
```

The paths declared to the runner do not replace the corresponding program
arguments. They tell the provenance layer what scientific role each file has.

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
./tools/lfhcal-run -j 4 jobs.txt
```

Lines are parsed with shell quoting, but are launched directly without a shell.
Pipes, redirection, variable expansion, and compound shell commands therefore
need an explicit shell payload, for example:

```text
bash -lc './analysis input.root > analysis.log 2>&1'
```

## HTCondor

The same job file can be submitted to HTCondor:

```console
./tools/lfhcal-run --condor jobs.txt
```

The initial backend assumes that the repository, campaign directory, data, and
outputs are on a filesystem shared by the submit and execute hosts. For a BNL
container wrapper:

```console
./tools/lfhcal-run \
  --condor \
  --condor-wrapper /path/to/run_in_eic_container.sh \
  --request-cpus 1 \
  --request-memory 4GB \
  jobs.txt
```

Site-specific submit entries remain configuration, not analysis knowledge:

```console
./tools/lfhcal-run --condor \
  --condor-extra 'requirements=...' \
  --condor-extra '+MyProject="LFHCal"' \
  jobs.txt
```

Use `--dry-run` to inspect the generated submit description without submitting.

## Provenance layout

By default each invocation creates:

```text
.lfhcal/runs/campaign-.../
  campaign.json
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
