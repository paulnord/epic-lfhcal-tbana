# Faithful Langau plotting: illustration methods

These fixed-parameter comparisons illustrate faithful drawing and numerical integration. They are stored on a separate evidence branch, not in the production code.

The simplified three-panel [main graphic](faithful-langau-explained.png) uses the same fixed parameter vector and validated numerical arrays as the problem-case figure below. It shows the peak region, 8–42 ADC, on identical axes: the old coarse drawing, the function actually fitted, and the independently converged Langau at the same parameters. The refined curve is a reference, not a replacement evaluator introduced by the plotting change.

Main example parameters: Landau width **0.121920**, MPV **22.555322**, normalization **13519.316**, Gaussian sigma **7.889414**, and width/sigma **0.01545361924**. No measured data are shown; no refit is performed.

Both examples freeze the previously published parameter vectors from cases A and C of [this provenance record](https://github.com/paulnord/epic-lfhcal-tbana/blob/0421e435a2fcba5942eea5abdab3e0c256259346/NewStructure/tests/fit-curve-evidence/fixed-fit-four-case-audit.json). No fits are performed. The problem case is a rounded historical parameter replay with no recovered measured histogram. The control is a saved synthetic fit, not measured data.

- Gray: old ROOT drawing, 1000 samples over 0–2000, using an in-memory copy of the same live callback.
- Orange: the faithful renderer samples the actual fitted legacy callback within its original 3.5–67.71 fit window.
- Blue: independently convergence-checked reference integral at the same parameters, retaining ROOT's Landau approximation, MP correction, normalization and ±5 Gaussian-sigma window.

The reference uses segmented 64-point Gauss-Legendre integration. Order 32 is checked at all 24001 grid points. Order 128 and independent segmented QUADPACK are checked at 153 positions per case; QUADPACK tolerance is varied and its reported error is retained. All current-renderer vertices are exactly equal to live TF1::Eval; parameters, fit range and Npx are unchanged. See [provenance.json](provenance.json) for full-precision inputs, checks and metrics.

The problem case's actual legacy evaluator differs by 48.00% of reference peak. The clean integration control agrees within 4.46e-9 of reference peak, although its coarse old drawing still differs by about 2.41% from the actual legacy function. Clean integration does not imply an exact old display or establish physical fit validity.

**This plotting change reveals existing integration distortions; it does not repair the integration or alter fitted parameters.**
