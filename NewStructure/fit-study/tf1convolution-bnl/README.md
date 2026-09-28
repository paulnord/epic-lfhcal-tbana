# TF1Convolution: isolated accuracy and speed benchmark

This is **not a production fitter change**. It is based on
`codex/adaptive-fit-clean` at `3a643646eb301c7112449e8f6d6ab31f12c72943`.
The candidate replacement is the small `TF1Langau.h` factory. The remaining
files are test infrastructure. `TileSpectra`, event selection, calibration
iterations, parameter-limit policies and production build targets are untouched.
The already-used EIC shell wrapper is copied unchanged from the earlier study.

## What is compared

| Label | Evaluator |
|---|---|
| `legacy100` | Original 100-midpoint, +/-5 Gaussian-sigma convolution |
| `adaptive5` | Existing `LangauNumerics.h`, production tolerance and +/-5 sigma |
| `fft10000` | ROOT `TF1Convolution`, fixed 10,000 samples |
| `fft32768` | Same, 32,768 samples |
| `fft65536` | Same, 65,536 samples |
| `fft131072_wide` | Twice the entire convolution domain, 131,072 samples |

The last pair approximately holds grid spacing constant while changing the
padding, so a domain/wrap-around effect is distinguishable from resolution.
The convolution domain is the fit interval padded by eight times the **allowed
maximum** Gaussian sigma on each side, fixed before minimization. Its actual
endpoints and spacing are recorded. This conservative choice can be expensive
and does NOT guarantee resolution of arbitrarily tiny allowed widths. The
synthetic stress tests deliberately investigate both tiny Landau and tiny
Gaussian widths. There is no claim that 10k or 64k is automatically sufficient.

Both factors are normalized; the Landau mode correction and public parameter
order `[width, MPV, area, sigma]` are preserved. Area multiplies the cached
convolution externally. The ordinary ROOT Gaussian is **untruncated**, whereas
the historical model integrates only +/-5 sigma. Therefore fixed-parameter
checks use BOTH the existing +/-5-sigma reference and an independent call to
the same integrator over +/-8 sigma. The latter approximates the untruncated
Gaussian. A truncation difference is reported separately, not hidden as an FFT
error. No RooFit data conversion is required.

## Controlled inputs and selection

Read-only inputs are the existing `adaptive-fullset-<code>-repro/refine5`
triggered histograms and `refine4` calibration text. Histograms are cloned,
not regenerated. Every engine gets the same native 1-ADC bins, same stored
errors, fit range, starting vector, parameter limits, Minuit2/Migrad settings,
and call budget. No 8/4/2/1 rebinning, sigma-floor experiment, retry cascade,
new fit-acceptance rule, or calibration propagation is applied.

Where an archived adaptive TF1 exists, its saved range and parameter bounds
are used. The cold starting vector follows the old rule: 3*pedestal sigma,
incoming global MIP average, fit-window counts, pedestal sigma. It is NOT the
already-minimized adaptive parameter vector. Where there was no saved TF1,
the original improved HGCROC range/bound rules are reconstructed from the
incoming calibration, native histogram, and mapping. Those cases are explicitly
marked `setup_source=reconstructed_original_rules`. The reconstructed versus
recorded setup difference is also logged for cases with a saved TF1. No
out-of-bounds starting values are silently clipped.

* `smoke`: E1 cells 896 and 903, B2 cell 131, E3 cell 2759: four frozen spectra.
* `survey`: all 14 FullSets; controls 965 and 1346 in each, the named problematic
  cells in `TARGETS`, plus each set's lowest- and highest-entry eligible spectra.
  Duplicate case selections are removed. Extremes are selected without testing
  whether a fit was saved. This is a deliberately enriched benchmark sample,
  **not** an estimate of population-wide fit efficiency.
* `stress`: synthetic parameter vectors only (ordinary, narrow Landau,
  very narrow Landau, tiny Gaussian). No detector input or minimization.

A saved fit is not scientific acceptance. All fit attempts, including failed
minimizations, covariance warnings, boundary hits, invalid curves and failed
peak/FWHM extractions remain in the outputs. Strict convergence and the old
status/bound check are reported separately; no 'best of several' calibration
is selected. This test does NOT run the full calibration pathway.

## BNL / tcsh: new working directory, no production rebuild

Run the worktree command once, from the existing checkout. It neither switches
nor rebuilds that checkout. If the new path/branch already exists, stop and
inspect it instead of forcing or deleting it.

```tcsh
set OLD = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-legacy-width-grid"
set FFTREPO = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark"
git -C "$OLD" fetch origin codex/tf1convolution-benchmark
git -C "$OLD" worktree add --track -b codex/tf1convolution-benchmark "$FFTREPO" origin/codex/tf1convolution-benchmark

setenv LFHCAL_WORK "/gpfs01/star/scratch/pnord/lfhcal"
setenv EIC_SHELL "$HOME/my_eic_work_with_LFHCAL/eic-shell"
cd "$FFTREPO/NewStructure/fit-study/tf1convolution-bnl"

python3 -m unittest -v test_benchmark.py
"$FFTREPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" python3 benchmark.py --self-test
```

The ROOT smoke test checks the FFT backend, ordinary-curve normalization,
parameter order, and TF1 copy/lifetime behavior. The C++ helpers are compiled
by ROOT's interpreter with optimization enabled. No Python callback implements
a convolution or runs inside the objective. FFT backend absence is fatal, so
ROOT's numerical-convolution fallback cannot masquerade as an FFT benchmark.

After those tests pass, make fresh outputs and run the four-spectrum smoke
benchmark. One repeat is for functionality; use three or more for timing.

```tcsh
set FFTSMOKE = "$LFHCAL_WORK/tf1convolution-smoke-`date -u +%Y%m%dT%H%M%SZ`"
"$FFTREPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    python3 benchmark.py --work "$LFHCAL_WORK" \
    --preset smoke --repeats 1 --out "$FFTSMOKE"
jq . "$FFTSMOKE/summary.json"
```

A synthetic resolution check, without rerunning fits:

```tcsh
set FFTSTRESS = "$LFHCAL_WORK/tf1convolution-stress-`date -u +%Y%m%dT%H%M%SZ`"
"$FFTREPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    python3 benchmark.py --preset stress --out "$FFTSTRESS"
```

## Broader comparison on Condor

The Yallfile runs **one job per FullSet, not per engine**. All engines for a
spectrum run sequentially on the same worker/core, with order deterministically
shuffled at each repetition. Each set uses three repetitions. Inputs are read
in place; nothing is copied to or overwritten in the calibration archive.

```tcsh
setenv LFHCAL_FFT_OUT "$LFHCAL_WORK/tf1convolution-survey-`date -u +%Y%m%dT%H%M%SZ`"
yall-run validate
yall-run plan
set FFTCAM = `yall-run create --campaigns-dir "$LFHCAL_FFT_OUT/campaigns"`
yall-run start "$FFTCAM"
yall-run status "$FFTCAM" -vv
```

Do not change this checkout while the benchmark is running. The summary job
writes `summary.json` and `all-fits.csv` at the survey root. A one-set local run
is also available with `--preset survey --datasets e1 --repeats 3 --out NEW_DIR`.

## Outputs and interpretation

* `manifest.json`: exact cases, setup origin, seeds/bounds/windows, input paths,
  histogram-content hashes, calibration/mapping hashes, ROOT version, source
  hashes, git state, host, settings and command line.
* `probes.csv`: evaluate ALL engines at the SAME parameter vector before
  minimization. Includes errors against +/-5 and +/-8 references, domain/spacing,
  cold setup + first evaluation time, warm cached spectrum-evaluation time,
  and spectrum-evaluation time after changing width (forcing FFT reconstruction).
* `fits.csv`: per-attempt CPU/wall time, construction time, function calls,
  status, covariance quality, EDM, parameter values/errors/covariances, bounds,
  raw ROOT chi2/NDF, each engine's peak/FWHM and the accurate +/-8-sigma
  peak/FWHM at that engine's fitted parameters. Weka missing token is `?`.
* `summary.json`: paired speedups versus adaptive, convergence counts and
  discrepancies. Failed attempts are not removed from overall timing summaries.
  Parameter comparisons use pairs for which both strict optimizer checks pass.

A common Poisson deviance is also recomputed for every solution using the
+/-8-sigma reference at the original bin centres, including empty bins.
`common_reference8_ndf` is explicitly number of included bins minus four;
it need not be identical to ROOT's saved NDF convention. This common score
prevents an inaccurate evaluator from winning merely by exploiting its own
quadrature error. It is a numerical/model-comparison diagnostic, not a new
production goodness-of-fit criterion.

File reads, JIT startup, a generic fitter warm-up, post-fit numerical checks,
peak extraction and report writing are outside `fit_wall_s`/`fit_cpu_s`.
The first FFT construction needed by a real fit is INSIDE fit timing. The
separate `construction_wall_s` allows total setup+fit costs to be compared.
Peak-finding alone tolerates roundoff-level negative FFT tail values; the
fit callback and the saved raw curve-error metrics are not clipped.

Do not treat old copied TF1s as executable reference functions. We reconstruct
all callbacks from source; archived TF1s supply metadata only. Production ROOT
serialization of an adopted FFT TF1 is a separate follow-up test, not yet claimed
by this harness. BNL runtime results and the ROOT self-test remain necessary;
the lightweight Python tests alone do not establish numerical accuracy.

ROOT primary references:
- https://root.cern/doc/master/classTF1Convolution.html
- https://root.cern/doc/master/TF1Convolution_8cxx_source.html
- https://root.cern/doc/master/fitConvolution_8C.html
- https://root.cern/doc/master/classTH1.html
