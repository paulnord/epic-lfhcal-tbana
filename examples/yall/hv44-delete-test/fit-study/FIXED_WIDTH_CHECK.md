# Fixed-parameter curve and width check

`check_fixed_widths.C` reads the existing `np100.csv`, `np1000.csv` and
`np10000.csv` files produced by `fit_cell903`. It preserves their fitted
parameter vectors, uses no histogram, performs no fit, and leaves their
original peak/FWHM/status fields unchanged.

## Run on BNL

`OUT903` must be the existing directory containing those three CSVs.
`EIC_SHELL` is the existing workspace launcher. No CMake build is necessary.

```tcsh
set TEST = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tbana-delete-test"
set STUDY = "$TEST/examples/yall/hv44-delete-test/fit-study"
ls "$OUT903/np100.csv" "$OUT903/np1000.csv" "$OUT903/np10000.csv"
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" /usr/bin/env CELL903_CSV_DIR="$OUT903" root -l -b -q "$STUDY/check_fixed_widths.C"
```

The macro prints a summary and creates `fixed-width-check.csv` inside `OUT903`.
It refuses an existing output path. For another run, pass a new path with
`/usr/bin/env CELL903_CSV_DIR="$OUT903" CELL903_WIDTH_REPORT="/new/report.csv"`.
It never overwrites a calibration file or source CSV. A failed numerical check
returns exit code 2; a report may contain partial rows if a later case fails.

## What is tested

The adaptive integral uses ROOT's standard `TMath::Landau` density, but not the
legacy fixed grid. A change of variable to the Landau's own width scale and
explicit core/tail breakpoints keep a narrow core visible to the quadrature.
Each panel uses a 16-point Gauss-Legendre rule, compared with two half-panels;
subdivision continues until the local absolute/relative error criterion is met.
The quadrature error estimate is empirical, not a mathematical error bound.

The main calculation preserves the original +/-5 Gaussian-sigma interval.
Two independent executions with relative tolerances 1e-8 and 1e-10 are compared.
A separate +/-8 sigma calculation tests integration-interval truncation; it is
not silently substituted for the original domain.

The peak is bracketed using a coarse survey and then refined by golden-section
search. Resolved multiple peaks cause a failure rather than an arbitrary width.
The search expands outward from the peak to bracket both half-height crossings,
then uses bisection. Returned endpoints must straddle the peak and each have
`f(endpoint)/f(peak)` within 1e-8 of 0.5.

`numerics_pass=1` additionally requires a peak change below 0.001 ADC, FWHM
change below 0.0001 ADC, and maximum function change below 1e-7 of peak height
when integration tolerances are tightened. Function comparisons use 129 grid
coordinates from MP-4*scale to MP+8*scale plus MP, MP+1 and the peak/crossings.
This finite sampling is not a universal convergence guarantee. The comparison
against the source fixed grid and the +/-8 sigma changes are recorded separately.

The original `legacy_fit_gate_pass` is preserved as `source_gate`. A numerical
PASS here does not change a rejected fit to an accepted calibration, establish
fit optimality, determine accurate parameter errors, reproduce the production
workflow, or establish a CPU/ROOT minimizer defect.

## Controls and local validation

Before analyzing CSVs, the macro runs four analytic Gaussian-width controls and
20 finite-interval Gaussian-Gaussian convolution controls. These exercise both
sides of the broad/narrow scale ratio. The convolution control uses the exact
finite interval, not an infinite-domain approximation.

The same ROOT-independent core can be checked with:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -pedantic test_fixed_width_numerics.cc -o /tmp/test_fixed_width_numerics
/tmp/test_fixed_width_numerics
```

The core controls passed locally with GCC. Additional local tests used an
independent transcription of CERNLIB's Landau approximation: the two previously
reported production parameter vectors reproduced the BNL high-resolution
function values and FWHMs. CSV handling was exercised with quoted seed labels,
NaNs preserved as strings, and refusal to overwrite an existing report. These
are local diagnostic tests, not a completed run of the user's six CSV rows with
ROOT on BNL. The BNL command above uses the actual ROOT library and full-precision
parameter vectors in the user's CSVs.
