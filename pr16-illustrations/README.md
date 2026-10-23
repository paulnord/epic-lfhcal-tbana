# Faithful Langau plotting: illustration methods

The [main graphic](faithful-langau-explained.png) compares three fixed-parameter Langau examples. Gaussian sigma is **8.0**, MPV **25**, and normalization **13519.316** throughout. Landau widths **0.08**, **0.16**, and **0.24** give width/sigma ratios **0.01**, **0.02**, and **0.03**. No measured data are shown and no fits are performed.

Each row uses identical parameters for all three columns, with a common 0–65 ADC display window and identical axes:
- Gray: the old ROOT drawing, 1000 samples over 0–2000 ADC, obtained from an in-memory copy of the same live callback.
- Orange: the actual legacy 100-point integration callback, evaluated directly at 26001 positions.
- Blue: a converged reference retaining ROOT's Landau approximation, MP correction, normalization and the same ±5 Gaussian-sigma integration window. The faint blue line in the middle column is this reference.

The reference uses segmented 64-point Gauss-Legendre integration. Order 32 is checked at all 26001 positions; order 128 and independent segmented QUADPACK are checked at 153 positions per case. QUADPACK tolerance is also varied. Every orange ordinate is checked against live TF1::Eval; the source function's parameters, range and Npx remain unchanged. See [lineup-validation.json](lineup-validation.json) for the parameter vectors, convergence checks and distinct integration/display-error metrics.

**Faithful plotting reveals the function's existing integration distortions. It does not repair the integral or alter a fit.** These illustration assets are separate from the production code.

## Earlier problem case and clean control

The earlier [problem-case](problem-case.png) and [clean-control](clean-control.png) figures and their evidence remain available below.

Both examples freeze the previously published parameter vectors from cases A and C of [this provenance record](https://github.com/paulnord/epic-lfhcal-tbana/blob/0421e435a2fcba5942eea5abdab3e0c256259346/NewStructure/tests/fit-curve-evidence/fixed-fit-four-case-audit.json). No fits are performed. The problem case is a rounded historical parameter replay with no recovered measured histogram. The control is a saved synthetic fit, not measured data.

- Gray: old ROOT drawing, 1000 samples over 0–2000, using an in-memory copy of the same live callback.
- Orange: the faithful renderer samples the actual fitted legacy callback within its original 3.5–67.71 fit window.
- Blue: independently convergence-checked reference integral at the same parameters, retaining ROOT's Landau approximation, MP correction, normalization and ±5 Gaussian-sigma window.

The reference uses segmented 64-point Gauss-Legendre integration. Order 32 is checked at all 24001 grid points. Order 128 and independent segmented QUADPACK are checked at 153 positions per case; QUADPACK tolerance is varied and its reported error is retained. All current-renderer vertices are exactly equal to live TF1::Eval; parameters, fit range and Npx are unchanged. See [provenance.json](provenance.json) for full-precision inputs, checks and metrics.

The problem case's actual legacy evaluator differs by 48.00% of reference peak. The clean integration control agrees within 4.46e-9 of reference peak, although its coarse old drawing still differs by about 2.41% from the actual legacy function. Clean integration does not imply an exact old display or establish physical fit validity.

**This plotting change reveals existing integration distortions; it does not repair the integration or alter fitted parameters.**
