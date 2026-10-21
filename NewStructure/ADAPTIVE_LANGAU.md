# Reviewable adaptive Landau–Gaussian integration

This is an isolated numerical revision, not a replacement minimizer or a Moyal
model. It ports the existing `AdaptiveLangau.h` unchanged from
`paulnord/epic-lfhcal-tbana` commit
`c986e5a5f2e010ad4e778f307216d4dad9e3e0a0` and wires it into current upstream
`eic/epic-lfhcal-tbana` base `92df3e48b84204dfacf0aa579893d379db5c5919`.
The earlier helper was extracted from `LangauNumerics.h` at `3a643646`.

## Pending upstream dependencies

This draft is layered over `review/upstream-92df3e4-pr86-pr87` at
`6be44e60b7e852b13d78554a97ddf08bf15c6ed3`: upstream `92df3e48` plus
[PR #86](https://github.com/eic/epic-lfhcal-tbana/pull/86) at `f81708c` and
[PR #87](https://github.com/eic/epic-lfhcal-tbana/pull/87) at `9bdb828`.
Both dependencies are still unmerged. The snapshot is only a comparison base in
Paul's fork; it does not change upstream or `main`. Buffer-lifetime cleanup and
checked output handling belong to those dependencies, not the adaptive diff.
After they merge, retarget/rebase onto the accepted upstream versions and recheck.

## Switch and intended adoption

The review patch defaults to **legacy**. Build two independent directories to
compare identical inputs without rebuilding or overwriting a running campaign:

```sh
git submodule update --init --recursive
cmake -S NewStructure -B build-legacy -DCMAKE_BUILD_TYPE=Release \
  -DLFHCAL_USE_ADAPTIVE_LANGAU=OFF
cmake --build build-legacy --target DataPrep Convert -j 4
cmake -S NewStructure -B build-adaptive -DCMAKE_BUILD_TYPE=Release \
  -DLFHCAL_USE_ADAPTIVE_LANGAU=ON
cmake --build build-adaptive --target DataPrep Convert -j 4
```

Run the same DataPrep command with the respective executable and separate output
paths. There is no new command-line argument. CMake reports the chosen mode;
adaptive HGCROC TF1s retain their names and get an explicit evaluator title.
The definition is PRIVATE to the LFHCAL library, so all three Analyses.cc callers
of FitMipHG use the same selection without mutable global state or extra API.

The intended endpoint is adoption as the default after review and real-data
comparison. That needs only `OFF` → `ON` in the CMake option declaration. Keep
an explicit `-DLFHCAL_USE_ADAPTIVE_LANGAU=OFF` for reproducibility. CMake caches
existing values, so changing the source default affects fresh build directories,
not an existing cache explicitly or implicitly set to OFF.

## Deliberately narrow scope

- HGCROC HG MIP fits alone select adaptive quadrature when enabled.
- Peak and FWHM use the same continuous adaptive curve as the fit, not the
  undersampled legacy callback. This extraction is part of the correction.
- CAEN HG, the newer CAEN pedestal model, LG, and the legacy callbacks stay intact.
- Four parameters, MPV shift, normalization, and ±5 Gaussian-sigma span stay the
  same. The kernel uses dimensionless Landau coordinates, explicit peak/tail
  subdivisions, a 16-point Gauss-Legendre rule, and relative tolerance `1e-10`.
- Fit windows, seeds, parameter limits, bins/errors, likelihood flags, optimizer,
  fit-status acceptance, bad-channel handling, and iteration count are unchanged.
- No FFT, Moyal model, extra Gaussian floor, rebinning, or fit-range correction is
  bundled here. Campaigns, plotting revisions, and unrelated bug fixes are excluded.
- No data schema or ROOT class version change, TileSpectra.h change, or new library
  dependency. PR #86 supplies automatic fit-buffer lifetime, including the
  seven-parameter HG buffers; this adaptive change relies on it for safe exits.
- An adaptive numerical failure rejects that fit, clears its saved-fit flag, and
  leaves previous calibration and caller outputs untouched. It does not silently
  fall back to legacy. Unrelated CAEN exceptions keep their previous behavior.

`AdaptiveLangau.h` is the only new production header; the only existing production
files changed are TileSpectra.cc and CMakeLists.txt. A compiled TF1 callback copied
in the same process remains live; a streamed/reloaded TF1 is not promised to be a
live refittable callback. Separate faithful-plotting work is not included here.

## Reproducible validation

From a ROOT-enabled shell, with compiler and ROOT versions consistent:

```sh
bash NewStructure/tests/adaptive-langau/run.sh "$PWD/build-legacy" legacy
bash NewStructure/tests/adaptive-langau/run.sh "$PWD/build-adaptive" adaptive
```

The runner builds only test executables in a temporary directory, does not fetch
inputs or run a campaign, and fails on a failed assertion. It runs:

1. 515 ROOT-free analytic/control/failure assertions on the real numerical helper.
2. 816 ROOT checks, including actual TMath::Landau, tolerance tightening, known
   returned-parameter peak/FWHM controls, legacy undersampling, and TF1 copy behavior.
3. Actual FitMipHG synthetic fits through the selected production library: initial
   and improved HGCROC, ordinary/pedestal CAEN HG and LG, adaptive failure
   rollback, and a successful fit after an aborted fit.
4. An independent 100,000/200,000-step midpoint reference and evaluation benchmark.
   Its printed timings are informational, not timing-sensitive pass/fail gates.

The benchmark compares the actual legacy callback to the adaptive kernel at four
width ratios. Adaptive evaluation costs more per call; integration accuracy, not
speed, is the purpose. These are not full-chain BNL runtime predictions.

Local validation and remaining limits are recorded in the accompanying review
report. Passing synthetic tests does not establish calibration acceptance or
convergence on beam data. Before adopting the new default, compare frozen spectra
(including the difficult narrow-width channels) and real calibration chains with
identical fit windows and iteration counts. Retain per-build commit, CMake cache,
ROOT/compiler versions, and separate output paths. Nothing in this kit launches,
publishes, or overwrites a campaign.
