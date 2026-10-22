# PR #90 comparison on local BNL data

`run_real_data.py` builds and runs the **real `HGCROCStudy` waveform analysis** at
the same two immutable commits as the synthetic benchmark:

- Base: `92df3e48b84204dfacf0aa579893d379db5c5919`
- PR #90: `3f33c280f056d3c65aeea50315667b08bc082441`

This companion measures **end-to-end elapsed time and per-process peak RSS**.
It includes startup, event I/O, analysis, plotting, writing, and shutdown; there
is no isolated plotting timer or excluded warmup. It also compares the complete
relative plot filename sets and SHA-256 hashes across trials. It **does not
compare ROOT histogram contents or prove that in-memory histogram state was
unchanged**. Use the synthetic runner for its dedicated caller/saved-state checks.

## Start with a bounded smoke comparison

Use Python 3.10+, Git, CMake, a C++ compiler, and your normal compatible ROOT
environment on Linux (or macOS). Keep this script beside
`run_pr90_benchmark.py`; it imports the pinned checkout/build-environment helpers.
Run on a suitable allocated compute node according to BNL policy, not an
inappropriate login node. The script does not log into BNL, submit jobs, copy
your input elsewhere, or contact data services. Git clones use the configured
repository URL.

```sh
# Activate your existing ROOT environment first.
python3 run_real_data.py --check-only

# First run: two processes, at most 1000 events each.
# Replace these example paths with your existing local paths.
python3 run_real_data.py \
  --input /absolute/path/to/converted_hgcroc_run.root \
  --runlist /absolute/path/to/matching_runlist.txt \
  --max-events 1000 --trials 1 --jobs 2 \
  --out /absolute/path/to/new/pr90-smoke
```

The input is an already converted HGCROC ROOT file with the expected `Setup`
and `Data` trees and a usable `Calib` tree. If calibration comes from a separate
ROOT file, add `--calibration /absolute/path/to/calibration.root`. The run list
must contain the run number in the data and correct metadata, including sample
count. Prefer a data/run-list/calibration combination that already works with
your normal `HGCROCStudy` workflow. This does not convert raw data or validate
the contents/schema of those inputs before launching ROOT.

Even a 1000-event smoke run may produce many per-layer plots and use substantial
memory/disk. Event count is not a plotting-memory bound. The direct CLI defaults
to 1000 events; use `--max-events 10000` for a larger sample, or explicitly
`--all-events` for the full file. Three trials per version is the default:

```sh
python3 run_real_data.py \
  --input /absolute/path/to/converted_hgcroc_run.root \
  --runlist /absolute/path/to/matching_runlist.txt \
  --max-events 10000 --trials 3 --jobs 2 \
  --out /absolute/path/to/new/pr90-measurement
```

Use `--dry-run` with the same input options to print the resolved command and
plan without checking input existence, cloning, building, writing, or running.
`--check-only` checks dependencies; with input options, it also validates that
the named files exist. Neither mode verifies ROOT data semantics.

## What gets run, and why

Each executable receives an argument array equivalent to:

```text
HGCROCStudy -w -i INPUT -r RUNLIST -o TRIAL/analysis.root -O TRIAL/plots -F png -L 1000
```

`-C CALIBRATION` is added when requested. These are verified options in the
[pinned HGCROCStudy source](https://github.com/eic/epic-lfhcal-tbana/blob/92df3e48b84204dfacf0aa579893d379db5c5919/NewStructure/HGCROCStudy.cc).
`-r` is implemented in `getopt` and its switch even though absent from that
version's help output. `-F png` overrides the upstream PDF default. Waveform mode
`-w` calls `MultiCanvas::PlotCorr2DLayer`, the method changed by #90.

In waveform mode, `-o analysis.root` produces **`analysis_Hists.root`**, not
necessarily `analysis.root`. This follows `CheckAndOpenIO` in the
[pinned waveform implementation](https://github.com/eic/epic-lfhcal-tbana/blob/92df3e48b84204dfacf0aa579893d379db5c5919/NewStructure/HGCROC_Waveform_Analysis.cc).
The runner requires a nonempty `analysis_Hists.root` and at least one nonempty
`Waveform_*` plot before accepting a trial. A detector configuration unsupported
by the plotting method, or completely masked data, may fail this check.

## Isolation and measurement

- Existing source checkouts are never switched or edited. Two fresh clones are
  pinned and checked for exactly the intended two-file signature change before
  separate Release builds of the `HGCROCStudy` CMake target.
- You may pass `--repo /absolute/path/to/your/existing/checkout` to clone locally.
  It must contain both pinned commits; missing commits require the helper's
  GitHub fetch fallback. Uncommitted edits in that checkout are not benchmarked.
- Every process gets a new trial directory, also used as its working directory.
  Both versions read the same resolved absolute input paths. No force-overwrite
  flag is used. Existing output directories cause an error; choose a new name.
- Output paths must contain only ASCII letters, digits, `/`, `_`, `.`, and `-`.
  The upstream code builds an unquoted shell `mkdir` command for plot directories,
  so paths with spaces or shell punctuation are deliberately rejected. Inputs
  can have spaces because they are passed as separate argv entries. Output
  directory names also cannot contain `.root`: upstream substitutes every such
  substring when deriving the histogram output filename, including directories.
- Each child prepends its own pinned build directory to `LD_LIBRARY_PATH` and
  `DYLD_LIBRARY_PATH`, retaining the rest of your environment. This prevents a
  previously activated LFHCAL build from overriding the intended variant through
  those library search paths. The resulting paths are recorded per process.
- Runs are sequential, alternating `base, pr90` for the first pair and
  `pr90, base` for the second. There is no simultaneous A/B resource contention.
- Wall time uses a monotonic clock around one child process. `os.wait4` collects
  that PID's resource usage, avoiding cumulative `RUSAGE_CHILDREN` contamination
  from previous builds/trials. `ru_maxrss` is normalized to KiB on Linux/macOS;
  it is the OS-reported child peak, not a sampled sum of an entire process tree.
- Input file hashes are recorded before and after all trials, and file stat
  metadata is checked before each trial. Do not edit/replace inputs during a run.
  These checks are not a filesystem snapshot or lock. Hashing is outside timing
  but reads inputs and therefore warms filesystem caches. Later runs may still
  have different cache behavior. Use a quiet, consistently allocated node and
  inspect per-trial spread, not only medians.
- The upstream analysis enables ROOT implicit multithreading. Keep CPU allocation
  and ROOT/runtime environment constant for both versions. Total process peak
  memory may be dominated by other stages, hiding a smaller plotting-only gain.

## Results and limitations

The output directory contains `environment.json`, per-build logs, per-trial
`run.log` and `measurement.json`, the real ROOT/plot outputs,
`completed_trials.json`, `input_snapshot_after.json`, `trials.csv`, and
`summary.json`. Each completed trial remains available if a later trial fails.

`summary.json` reports median/min/max total seconds, median peak RSS, base/PR
speedup, RSS reduction, and these separate checks:

- `input_files_unchanged_on_disk`: recorded input files matched the before/after
  hashes and metadata. This is not an in-memory histogram-state check.
- `plot_files_equal` and `plot_bytes_equal`: complete relative plot filename sets
  and hashes match across all base/PR trials. Equal PNG bytes are a strong check
  of those generated images, not proof of saved ROOT histogram equality.
- `root_histogram_semantics_checked` is always **false** in this companion.

Exit 0 means the measurements completed with zero analysis exit statuses,
required nonempty outputs, and matching plot file sets/bytes. **It is not a
physics/correctness PASS.** A plot mismatch returns exit 3 after saving timing
results and is printed as `REVIEW`; inspect the plots before
concluding a regression. PDF metadata can differ without a visual difference,
so PNG is the normal mode. ROOT file byte comparisons would likewise be
misleading because metadata and object serialization can differ. Perform your
usual saved-histogram/physics validation separately.

## Optional reproducible JSON configuration

For additional verified waveform flags, copy `real_data.example.json`, replace
the example absolute input paths, and run:

```sh
python3 run_real_data.py --config my-run.json --trials 1 --out /absolute/path/to/new/pr90-json-smoke
```

The example limits each process to 1000 events. `inputs` declares absolute local
file paths; `argv` is an array, never a shell string. `{exe}` is the pinned build
and `{output}` is the fresh trial directory. File options must reference exact
named placeholders. Output arguments are fixed to `{output}/analysis.root` and
`{output}/plots`; `-w`, `-i`, `-r`, `-o`, `-O`, and `-F` are mandatory. Supported
optional flags are `-C`, `-B`, `-k`, `-t`, `-l`, `-d`, `-E`, `-L`, `-q`, `-Q`,
`-s`, and `-c`. Refer to the pinned source for their scientific meaning. This is
not a generic arbitrary-program runner. Force overwrite (`-f`), other analysis
modes, duplicate flags, and unknown options are rejected. To use all events in
a JSON configuration, remove the `-L` and its value deliberately.

For external calibration, add `"calibration": "/absolute/path/to/calibration.root"`
to `inputs` and `"-C", "{calibration}"` to `argv`. All inputs are required to be
used and are included in the before/after hash record. Do not combine `--config`
with direct input/event-limit CLI options.

## Validation status

`python3 -m unittest -v test_real_data.py` tests the orchestration without ROOT,
including real subprocess timing/RSS isolation, argument/path safety, output
requirements, plot comparisons, and a mocked-build end-to-end fixture. These
are **not** real HGCROC physics tests. The actual pinned ROOT build and BNL data
execution require your ROOT environment and data; no timing result is claimed
until you run them there.
