# Minimal adaptive Langau patch kit

**Activation is explicit. Checking out this branch alone does not change the
production fitter. Run `python3 apply_adaptive_minimal.py --apply` once in the
new worktree, then review the small `git diff`.** The helper, installer, tests
and this note are committed; the installer makes the core-file edit locally.
No production branch, running checkout, calibration input, or ROOT installation
is modified by downloading the kit.

Base: original `main`, commit `924ad82de6d150534b4d7684b5638df92c0a2016`.
The installer accepts exactly two TileSpectra.cc base blobs: the original
`80fdbaca75d727e9d7451c3d5e3d0626d1d13808` and its stack-array cleanup
`594403ddae0b318c013e7ea7145087b4fdcf7188`. It will not silently patch the FFT,
sigma-floor, or older adaptive implementation instead.

## Compiler warning cleanup (2026-10-06)

The base source now uses stack arrays for temporary fit ranges, initial values
and limits in the HG/LG fitters. This removes mismatched scalar deletes and
early-return leaks without changing fit windows, parameters, or acceptance.
The histogram pointer tables in Analyses.cc and HGCROC_Convert.cc now use
standard vectors/arrays in place of 14 variable-length arrays; histogram
ownership and indexing are unchanged.

Validation: all three changed C++ translation units, plus the generated
adaptive TileSpectra.cc, compile to objects with GCC 13 and ROOT 6.40.00,
with `-Werror=vla -Werror=mismatched-new-delete`. Nine installer tests pass.
The updated installer produces byte-identical adaptive output from the original
base; output from the cleaned base differs only in the LG temporary-array
cleanup. These checks do not replace a full BNL build or real-data replay.
Keep the shared BNL build fixed while campaigns are running; apply and rebuild
this cleanup after those campaigns finish.

## Production scope

One new 191-line header, `AdaptiveLangau.h`, and a small patch to ONE existing
file, `TileSpectra.cc`. There is no second implementation of `FitMipHG`, no new
persistent member, no TileSpectra.h change, and no CMake/library dependency change.

The core patch:

1. Selects the adaptive callback for HGCROC HG fits. CAEN keeps `langaufun`.
2. Gets HGCROC ScaleH and FWHM from the same continuous adaptive model, using
   the earlier bounded maximum/half-height procedure. It does not fit a second
   function, use a sampled graph maximum, or call the old 100-step evaluator
   after completing an adaptive fit. CAEN retains its original peak routine.
3. Uses stack arrays in FitMipHG (already present in the cleaned base) and catches numerical exceptions. A numerical
   failure clears the saved-fit flag, reports the cell and reason, and leaves
   the previous calibration and caller outputs unchanged. Stack arrays also
   remove the original scalar-delete-on-array problem and early-return leaks
   in this function. The installer leaves FitMipLG unchanged, including its
   stack-array cleanup when starting from the cleaned base.

The four parameters remain `[Landau width, Landau MPV, area, Gaussian sigma]`.
The Landau location is `MPV + 0.22278298*width`. Normalization and integration
interval `x +/- 5*Gaussian sigma` are unchanged. The callback has no mutable
shared state and owns no ROOT object. The saved TF1 name is unchanged; its title
identifies the adaptive evaluator. As with other compiled TF1 callbacks, a
streamed/reloaded TF1 must not be mistaken for a live refittable callback.

Fit windows, initial values, physical parameter limits (including the ORIGINAL
Gaussian lower limit), histogram bins/errors, likelihood flags, minimizer
configuration, fit-status/boundary policy, bad-channel map, event selection and
calibration iteration count are untouched. In particular the existing `M` flag
is not removed, and there is no new width floor, minimum-hit cut, FFT retry,
8/4/2/1 rebinning, or added noise model.

## Numerical implementation and validation boundary

The helper is extracted from the convolution and peak-search parts of
`LangauNumerics.h` at `3a643646eb301c7112449e8f6d6ab31f12c72943`, not an unrelated
adaptive integration scheme. It retains dimensionless Landau coordinates,
explicit core/approximation-boundary and tail breakpoints, adaptive subdivision
of the 16-point Gauss-Legendre rule, `1e-10` relative tolerance, evaluation/depth
budgets, and the earlier continuous peak/FWHM algorithm. Diagnostic counters,
verification wrappers, and repeated +/-8/tighter-tolerance validation passes
are not on the production fit path. They do not select alternative fits.
Finite-value and numerical-convergence checks remain mandatory.

Therefore this is a smaller packaging of the numerical correction, NOT a claim
of bit-for-bit identity with every acceptance check in `adaptive-fit-clean`.
Peak/FWHM extraction is explicitly part of the correction, not concealed as
an integrator-only one-line change.

Initial patch-kit validation: 515 checks of the actual C++ helper against closed-form
finite-span Gaussian convolution, area/translation behavior, tighter quadrature,
peak/FWHM and failure cases. These passed both optimized and AddressSanitizer +
UndefinedBehaviorSanitizer builds. Six Python source-patch tests passed; those
test transformation scope, not ROOT behavior. ROOT was unavailable in the authoring
environment at that stage; the ROOT macro, patched production build, real-data
replay, runtime comparison and full calibration-chain regression were deferred
to BNL. The compiler-cleanup validation above is a separate, later check.

The ROOT macro uses real TMath::Landau, ordinary/narrow/broad-sigma cases,
`1e-10` versus `1e-12` evaluations, the E1 896/903 returned-parameter controls,
a case that exposes the historical 100-step defect, and an actual C++ TF1 copy.
It is not a replacement for a real-data fit regression.

## BNL tcsh: isolated checkout and activation

Use a new worktree. Do not overwrite or force an existing worktree/branch.
The existing FFT worktree supplies only its already-tested container wrapper.

```tcsh
set OLD = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-legacy-width-grid"
set MINREPO = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-adaptive-minimal"
set WRAP = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark/tools/run-in-eic-shell.sh"
setenv EIC_SHELL "$HOME/my_eic_work_with_LFHCAL/eic-shell"

git -C "$OLD" fetch origin codex/adaptive-langau-minimal
git -C "$OLD" worktree add --track -b codex/adaptive-langau-minimal "$MINREPO" origin/codex/adaptive-langau-minimal
cd "$MINREPO"
python3 -m unittest -v test_apply_adaptive_minimal.py
python3 apply_adaptive_minimal.py --apply
git diff --stat
git diff -- NewStructure/TileSpectra.cc
```

Apply exactly once. A second invocation refuses the changed source rather than
applying it twice. The original file is recoverable from git; the installer
never resets other edits or commits on your behalf.

## Test, then build

```tcsh
mkdir -p "$MINREPO/build-minimal-tests"
"$WRAP" "$EIC_SHELL" c++ -std=c++17 -O2 NewStructure/tests/test_adaptive_minimal.cc -o build-minimal-tests/test_adaptive_minimal
"$WRAP" "$EIC_SHELL" ./build-minimal-tests/test_adaptive_minimal
"$WRAP" "$EIC_SHELL" root -l -b -q 'NewStructure/tests/test_adaptive_minimal_root.C()'
```

Stop on a failing test. After successful ROOT checks:

```tcsh
git submodule update --init --recursive
"$WRAP" "$EIC_SHELL" cmake -S NewStructure -B NewStructure/build
"$WRAP" "$EIC_SHELL" cmake --build NewStructure/build --target DataPrep -j 4
```

This does not launch calibration jobs. Review and commit the TileSpectra.cc edit
on this test branch before a production-style replay so its provenance is pinned.
Keep the old calibration inputs read-only. Compare against both legacy100 and
existing adaptive results on frozen spectra before changing selection or running
an entire calibration chain.
