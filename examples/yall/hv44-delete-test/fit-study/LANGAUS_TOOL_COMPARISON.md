# Landau--Gaussian tool comparison

`compare_langau_tools.py` is a standalone diagnostic for preserved HGCROC
histograms. It fits the histogram with the legacy 100 midpoint sample,
the adaptive quadrature implementation, and ROOT `TF1Convolution`. It also
performs a bounded extended-likelihood fit with `RooFFTConvPdf`, and evaluates
the direct numerical convolution at the saved parameters. Direct
`RooNumConvPdf` minimization is deliberately not treated as production-ready
because the optimizer can probe parameter vectors for which its integrator
does not converge.

For the preserved E1 examples:

```bash
python3 examples/yall/hv44-delete-test/fit-study/compare_langau_tools.py \
  local-results/fullset-e1-review-20260921/imported/fullset-e1-repro/refine5 \
  local-results/langau-tool-comparison-legacy

python3 examples/yall/hv44-delete-test/fit-study/compare_langau_tools.py \
  local-results/fullset-e1-adaptive-review-20260921/imported/fullset-e1-repro/refine5 \
  local-results/langau-tool-comparison
```

The output is `results.json`. Cell 896 is included explicitly, along with
835, 898, 1223, and 640 when present. The legacy E1 cell-896 histogram is the
key regression: refitting it with adaptive quadrature moves from the narrow
legacy solution (width 0.122, MPV 22.56, Gaussian sigma 7.89; chi-square
13,584) to the smooth solution (width 1.328, MPV 13.66, sigma 2.50; chi-square
2,119). On the already-adaptive histogram, legacy and adaptive fits agree to
the displayed precision. The bounded RooFFT fit also converges for cell 896:
width 1.328, MPV 14.07, sigma 2.50, with a valid covariance matrix.
