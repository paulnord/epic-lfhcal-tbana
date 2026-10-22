# PR #90 plotting-copy benchmark

Run the real plotting wrapper before and after [PR #90](https://github.com/eic/epic-lfhcal-tbana/pull/90), with the same deterministic ROOT histogram input. No experiment data files are needed.

For your existing converted HGCROC data, use [REAL_DATA.md](REAL_DATA.md) and `run_real_data.py`. That companion runs the actual `HGCROCStudy` workflow on the same input file before/after the change. Its whole-job timing is separate from the controlled synthetic plotting measurement below.

## Get it at BNL

From any existing checkout, these commands fetch this benchmark into a **new detached worktree**. They do not switch or modify your current branch or working files. Choose an unused sibling directory if `../pr90-bench-tools` already exists.

```sh
git fetch https://github.com/paulnord/epic-lfhcal-tbana.git benchmark-pr90-plot-copies
git worktree add --detach ../pr90-bench-tools FETCH_HEAD
cd ../pr90-bench-tools/benchmarks/pr90_plot_copy
python3 run_pr90_benchmark.py --check-only
python3 run_pr90_benchmark.py --repo ../.. --out "$PWD/pr90-results"
```

Activate your usual BNL ROOT environment before running these commands. The scripts do not log into BNL, choose a batch queue, or submit jobs. Follow the site's policy for running a benchmark on a compute node rather than a shared login node.

## Run

Use Linux or macOS with Python 3.10+, Git, CMake 3.13+, and an existing ROOT 6 installation with development headers, CMake support, and batch PNG rendering. Activate the ROOT environment so `root-config` is on `PATH`; use the compiler that built ROOT, or set `CXX` to a compatible single compiler executable.

Unzip the bundle, keep its files together, then:

```sh
python3 run_pr90_benchmark.py --check-only
python3 run_pr90_benchmark.py --out pr90-results
```

The runner makes two fresh checkouts and builds `LFHCAL` from each. It never changes an existing checkout or branch, installs software, pushes commits, or modifies the PR. The output directory must not already exist. Network access is needed to clone the repository unless you supply an existing local checkout containing both commits:

```sh
python3 run_pr90_benchmark.py --repo /path/to/epic-lfhcal-tbana --out pr90-results
```

If that local repository lacks either pinned commit, the runner fetches it into the **new clone only**. Build and runtime failures leave their logs in the output directory; the runner does not silently work around failures or change source code.

## Size and repetitions

Defaults: 32 cells, one untimed warmup, five timed plotting calls per process, five separate processes per version. Trial order alternates base/PR, then PR/base. Both versions use the same ROOT installation, compiler, build type, fixture, and number of calls.

```sh
# Small smoke test, not a reliable performance measurement:
python3 run_pr90_benchmark.py --out pr90-smoke --cells 4 --iterations 1 --trials 1

# Larger map and longer trials; check available memory first:
python3 run_pr90_benchmark.py --out pr90-long --cells 64 --iterations 20 --trials 5
```

The main waveform array alone is about 4.36 MiB per cell, or 140 MiB for 32 cells, **per map copy**. The baseline can hold the caller's map, wrapper copy, and helper copy simultaneously. Other histograms and ROOT add to that. Allow several hundred MiB of RAM for the default, additional RAM for the build, and space for both source/build trees and per-trial ROOT output. Use `--jobs 1` if build memory is limited. Do not compare timings while the machine is swapping or under heavy competing load.

`--dry-run` prints the plan without writing anything or requiring ROOT. `--cells` is capped at 128 as a memory safeguard. For a scaling check, run the same command at 8, 16, 32, and 64 cells, using a different output directory each time.

## What it actually measures

Pinned revisions:

- Base: `92df3e48b84204dfacf0aa579893d379db5c5919`
- PR #90: `3f33c280f056d3c65aeea50315667b08bc082441`

The runner checks that these trees differ only by the intended two signature lines. It does not silently follow a newer branch head.

The C++ driver constructs real `TileSpectra` objects using the production HGCROC `ext=3` constructor, including its 550 × 1034 `TH2D` waveform. It fills every allocated histogram bin deterministically and adds waveform/profile structure plus underflow/overflow sentinels. It calls the actual `MultiCanvas::PlotCorr2DLayer` with a selected single cell. The whole map still passes through the production wrapper and retained by-value plotting helper, even though only cell 0 is drawn.

This is intentionally a controlled plotting workload that makes the extra full-map copy visible. It is **not** a replay of Run 165, a full detector analysis, a benchmark of all plotting configurations, or a claim that the same speedup applies to end-to-end processing. Histogram precision and binning are unchanged. The inner helper copy remains in both versions.

- `elapsed_seconds`: the repeated real plotting calls, including map copies, drawing, and PNG saving. Fixture creation, warmup, validation, and final ROOT saving are outside this timer.
- `peak_rss_kib`: process-lifetime high-water RSS sampled immediately after the timed loop, before final validation/ROOT saving. It includes ROOT startup, the fixture, warmup, and plotting. It is **not** an incremental allocation measurement. Linux KiB and macOS byte units are normalized to KiB.
- `process_wall_seconds`: total child process time, including setup and validation, recorded separately. Do not use this to isolate the copy cost.

Each trial is a new process, so one version cannot inherit the other's allocator high-water mark. Warmup reduces first-render startup effects in the timed section. Increase `--iterations` if timed trials are too short or noisy. All raw trial values are retained; the summary uses medians and reports the min/max plotting times.

## Correctness checks

For all ten active histograms/profiles in each fixture cell, the driver records streaming semantic checksums before and after plotting and after writing/reopening `after.root`. It includes every bin and flow bin, stored contents/errors, profile accumulators, entries/statistics, histogram type/name/title, axis binning/ranges/labels/styles, line/fill/marker settings, and function-list size. It exercises `TileSpectra::WriteExt(false)` and also explicitly writes the fixture's remaining initialized histograms.

The checksums exclude pointer addresses, directory ownership, ROOT file UUIDs, and timestamps. They are integrity checks, not a proof that every possible ROOT object field or fit is identical. This fixture contains no fitted functions. Per-histogram checksum manifests identify which object differs. Raw ROOT file bytes are not compared.

The runner also compares the final PNG files byte for byte across versions and repeated trials. Matching bytes demonstrate identical output for this fixture. If they differ, inspect the images; metadata differences alone are not proof of a visual regression.

## Results

Read `summary.json` and `trials.csv`. Each trial directory contains its PNG, `after.root`, semantic manifests, driver `result.json`, and `run.log`. The top-level directory also contains build logs and `environment.json` with pinned commits, ROOT/compiler details, arguments, and the driver checksum.

Exit status:

- `0`: all caller-state, ROOT read-back, cross-version semantic, and PNG checks passed.
- `1`: dependency, checkout, build, execution, or per-process validation failure. Check the indicated log.
- `2`: cross-version semantic mismatch.
- `3`: semantic checks passed but PNG bytes differ; visual review is needed.

Do not treat a failed correctness check as a successful performance result.

## Validation of this bundle

The Python runner was syntax-checked and passed nine ROOT-free orchestration tests, including real temporary Git clones, preservation of an existing dirty checkout, exact diff checking, per-build library-path isolation, result validation, and mismatch detection. Run them with:

```sh
python3 -m unittest -v test_runner.py
```

The driver was checked against the repository's actual APIs and independently source-reviewed. **The full ROOT build and this benchmark have not been executed here because ROOT and CMake are unavailable. No timing or memory reduction is being reported as measured.** A successful run in your ROOT environment is still required.
