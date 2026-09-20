# Adaptive HGCROC MIP fitting

`TileSpectra::FitMipHG` uses adaptive Landau–Gaussian convolution for HGCROC
readout, in both the initial and improved calibration stages. CAEN high- and
low-gain fitting continues to use the existing fixed convolution and width
search.

## Numerical implementation

`LangauNumerics.h` contains the standard-C++ implementation promoted from the
isolated convolution study. It retains the same four parameter definitions,
Landau maximum correction, normalization and integration interval of
`x ± 5 * GSigma`. Integration uses the Landau's own dimensionless coordinate,
explicit intervals around the narrow core and distribution approximation
boundaries, and adaptive 16-point Gauss–Legendre quadrature. The fit tolerance
is `1e-10`.

The peak is bracketed and refined by golden-section maximization. Each
half-height crossing is bracketed independently and refined by bisection.
The saved calibration width is the distance between those crossings.
Peak, width and curve values are checked against integration at `1e-12`.
An additional ±8-sigma evaluation is a diagnostic; it does not change the
fitted model or acceptance thresholds.

The existing fit ranges, starting values, parameter limits, likelihood,
minimizer options and call/iteration budgets are retained. No entry-count
threshold, physical background component or fit-quality selection is added.
`SetNpx(1000)` remains the saved/drawn curve sampling density; it is separate
from the adaptive integration used during minimization.

## Failure handling and calibration updates

HGCROC setup rejects nonfinite seeds, invalid pedestal widths, invalid ranges,
integrals that cannot safely enter the existing integer-area setup, and
invalid bounds before minimization. Numerical exceptions during fitting fail
the cell explicitly; the objective is not replaced by an arbitrary penalty.

The existing fit-status and boundary checks are followed by the numerical
peak/FWHM checks. Only a successful calculation updates `ScaleH`,
`ScaleWidthH`, caller output arrays and the accepted-model flag. A rejected
fit preserves the preceding calibration and cannot expose an earlier fit as
the current successful model. Diagnostic messages identify the cell and
failure stage. Automatic arrays in the HG routine avoid leaking setup memory
on these early returns.

These numerical checks establish consistency of the calculation. They do not
establish that the signal model describes a measured spectrum adequately, or
that the fitted parameters are globally unique.

## ROOT output

The fitted `TF1` retains its existing name, four parameters, limits and range.
Its title identifies adaptive integration, tolerance and Gaussian span.
No persistent data members or calibration text columns are added.

ROOT stores a sampled representation of a C++-callback `TF1` for subsequent
plotting and evaluation. The regression suite writes actual production fits
and reads them in a separate process, checking metadata exactly and comparing
bin-centre and off-grid evaluations with the accurate curve. The allowed
interpolation discrepancy is 0.1% of peak height, distinct from the much
tighter integration tolerance used while fitting. Refitting a reloaded
function, or changing its parameters, requires reconstructing its callback.

## Build and tests

Use an existing ROOT installation; no additional quadrature library or raw
HGCROC decoder is needed to build and test the histogram-fitting code:

```sh
cmake -S NewStructure -B NewStructure/build -DBUILD_TESTING=ON
cmake --build NewStructure/build --target \
  DataPrep test_langau_numerics test_adaptive_mip test_adaptive_root_roundtrip
ctest --test-dir NewStructure/build --output-on-failure
```

The tests cover analytic convolution/width controls, quadrature and peak-search
failures, deterministic spectra through the public production fit API, initial
and improved HGCROC stages, preservation of calibration on rejection, the
unchanged CAEN evaluator, and fresh-process ROOT persistence. Synthetic spectra
are generated numerically; no collaboration data are needed or included.

The optional decoder header is included only when `DECODE_HGCROC` is enabled,
matching the conversion implementation's existing guard. A decoder-disabled
build supports histogram fitting; it does not validate raw-data conversion.
