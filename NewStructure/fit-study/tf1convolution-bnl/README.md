# TF1Convolution: isolated accuracy and speed benchmark

This is **not a production fitter change**. The parent branch is
`codex/adaptive-fit-clean` at `3a643646eb301c7112449e8f6d6ab31f12c72943`.
The small candidate adapter is `TF1Langau.h`. Other files are test infrastructure;
`TileSpectra`, selection, calibration iterations and production targets are untouched.

## Important correction: FFT point-count overflow and nonfinite checks

The ROOT `TF1Convolution::MakeFFTConv` source inspected during the investigation
normalizes with `.../(fNofPoints*fNofPoints)`, multiplying two `Int_t` operands.
For a 32-bit signed integer the largest safe count is **46340**, not INT_MAX:
46340^2 = 2147395600; 65536^2 = 4294967296. Signed overflow is undefined behavior,
not a legitimate large-grid approximation. The exact compiled BNL behavior has
not been established by the Python stacks. This is a concrete upstream source
hazard and a plausible explanation, not a claimed native-stack diagnosis.

The earlier 65536/131072 experiments must not be trusted. Our old self-test also
used a `discrepancy > tolerance` comparison without rejecting NaN first; NaN could
therefore pass. The old pass message was not valid numerical certification.

The Python and C++ adapters now reject unsafe counts before constructing the
convolution. Every checked curve, timing-sweep checksum, normalization discrepancy
and lifetime comparison must be finite. Nonfinite probes stop that worker before
minimization; errors are not silently clipped or replaced with zero.

| Label | Evaluator |
|---|---|
| `legacy100` | Original 100-midpoint, +/-5 Gaussian-sigma convolution |
| `adaptive5` | Existing adaptive integrator, production tolerance and +/-5 sigma |
| `fft10000` | ROOT TF1Convolution, 10000 samples |
| `fft16384` | Same, 16384 samples |
| `fft32768` | Same, 32768 samples |
| `fft32768_wide` | Twice the full convolution domain, 32768 samples |

Compare `fft16384` with `fft32768_wide` for approximately equal grid spacing but
different padding. Compare 10000/16384/32768 on the original domain for sampling
resolution. Counts and domain stay fixed throughout each minimization. Safety
from integer overflow does **not** imply adequate resolution of the narrowest
allowed Landau/Gaussian width. Record actual spacing and compare curves.

The domain is the fit interval padded on each side by eight times the allowed
maximum Gaussian sigma, chosen before fitting. Both components are normalized;
parameter order remains `[Landau width, MPV, area, Gaussian sigma]`. The Landau
mode shift is preserved and area multiplies the cached convolution externally.
FFT uses an untruncated Gaussian; the original integrates +/-5 sigma. Fixed-vector
checks report differences against both +/-5 and +/-8 adaptive references.

## Inputs and controlled comparison

Read-only inputs are existing `adaptive-fullset-<code>-repro/refine5` triggered
histograms and `refine4` calibration text. All methods receive the same cloned
native 1-ADC count histogram, stored errors, range, seeds, bounds and Minuit
settings. No rebinning, sigma-floor experiment, rescue sequence or new scientific
acceptance rule is introduced. Saved TF1s provide metadata, not executable
reference callbacks.

Where a saved adaptive TF1 exists, use its recorded range/bounds. Otherwise the
original improved HGCROC setup rules are reconstructed and marked explicitly.
The cold seed is the old rule (3*pedestal sigma, incoming global MIP scale,
fit-window counts, pedestal sigma), not the already-minimized adaptive vector.

`smoke` selects E1 896/903, B2 131, E3 2759. `survey` selects controls 965/1346 in
all 14 sets, named problem cells and lowest/highest-entry eligible cells in each
set, independent of saved-fit status. `--cells` restricts to explicit cells in
selected datasets. This enriched sample is not a population efficiency estimate.
`stress` runs synthetic parameter probes without fitting, via `benchmark.py`.

## Run with the external supervisor (BNL / tcsh)

The checkout should already exist. Stop old jobs first; do not change this
checkout while workers are using it.

```tcsh
set FFTREPO = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark"
setenv LFHCAL_WORK "/gpfs01/star/scratch/pnord/lfhcal"
setenv EIC_SHELL "$HOME/my_eic_work_with_LFHCAL/eic-shell"
cd "$FFTREPO"
git pull --ff-only origin codex/tf1convolution-benchmark
cd NewStructure/fit-study/tf1convolution-bnl
python3 -m unittest -v test_benchmark.py

set FFTSMOKE = "$LFHCAL_WORK/tf1convolution-bounded-`date -u +%Y%m%dT%H%M%SZ`"
"$FFTREPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    python3 -u run_benchmark.py --work "$LFHCAL_WORK" \
    --preset smoke --datasets e1 --cells 896 903 \
    --methods adaptive5 fft10000 fft16384 fft32768 \
    --repeats 1 --fit-timeout 30 --check-timeout 60 --out "$FFTSMOKE"
jq . "$FFTSMOKE/summary.json"
```

No DataPrep rebuild: ROOT compiles the C++ helpers at startup. The supervisor
runs the corrected ROOT self-test first under a timeout, then freezes the case
manifest. Each (cell, method, repetition) runs in a **fresh executable process**,
sequentially on the same host; order is deterministically shuffled. ROOT/JIT
startup and input reads are outside fit timing, but increase total wall time.
Do not compare this total worker wall time with the measured minimization time.

Default budgets are 120 s startup/setup, 30 s fitting, 60 s checks, and 240 s total
per worker. Phase budgets accumulate across that worker's stages. The parent
prints stage changes plus a heartbeat every 10 s. It does not rely on a Python
thread/signal handler running while ROOT is executing: it can terminate the
worker process group (TERM, then KILL). Ctrl-C cleans up the active child.

A timeout is an explicit, censored observation, not a completed 30-second fit or
an invisible omitted case. Other methods/cells continue. No automatic retry is
made. Increase a budget deliberately in a fresh experiment when needed.

## Outputs

* `manifest.json`: cases/settings, source and input hashes, git state, ROOT
  version, host and timeout policy. Per-worker manifests preserve exact inputs.
* `logs/`: one log for each worker, including all ROOT warnings and tracebacks.
* `attempts/`: progress and partial-fit checkpoints; completed per-worker files.
* `probes.csv`: fixed-vector accuracy vs +/-5 and +/-8 references, FFT spacing,
  cold first evaluation and cached/changing-parameter sweep timings.
* `fits.csv`: fit CPU/wall time, status, covariance quality, EDM, calls, parameters,
  errors/covariance, peak/FWHM and common-reference deviance. Completed fit details
  survive a subsequent slow validation. Missing values are `?`.
* `summary.json`: cumulative counts, timeout/error counts, paired timing and
  answer comparisons, rewritten atomically after each worker.

`fit_wall_s`/`fit_cpu_s` time only `TH1::Fit`. The first convolution rebuild is
included; JIT/startup, construction, probes, diagnostics and reporting are not.
A killed fit has no completed time; `fit_time_censored` and the observed elapsed
fit-phase lower bound are separate. Paired speedups require actual fit timings;
timeout counts must be inspected rather than judging medians of survivors alone.

The common Poisson deviance uses the +/-8 reference at native bin centres,
including empty bins; its NDF is included bins minus four, not necessarily ROOT's
saved NDF convention. Strict status/covariance/bound checks and the legacy status
policy are reported separately. Neither means scientific acceptance.

## Condor

The Yallfile uses the supervisor with three repetitions per set. Validate and
plan before submitting; do not launch a full survey until the small test works.
`benchmark.py --collect DIR` still collects `DIR/<dataset>/fits.csv` into
`all-fits.csv` and a combined `summary.json`.

## Validation status

The pure-Python regression suite includes finite-value rejection, safe sample
counts, censored timing, checkpoint retention, and terminating a subprocess
blocked inside a compiled libc call. ROOT runtime checks and real-data validation
must run on the target ROOT installation. Production FFT TF1 serialization is
still a separate follow-up before adopting the adapter.

Primary references:
- https://root.cern/doc/master/TF1Convolution_8cxx_source.html
- https://root.cern/doc/master/TF1Convolution_8h_source.html
- https://docs.python.org/3/library/subprocess.html
