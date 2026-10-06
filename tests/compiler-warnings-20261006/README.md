# Compiler warning cleanup validation — 2026-10-06

PR: https://github.com/eic/epic-lfhcal-tbana/pull/86 (draft)

Base: `92df3e48b84204dfacf0aa579893d379db5c5919`
Patch: `a4cadde4b98c44efee2d88635903903f052dc954`

## Environment and scope

GCC 13, C++17, ROOT 6.40.00 from the PyPI ROOT wheel 0.1a12, Linux.
This is a local regression test, not the BNL production environment (Clang 20, ROOT 6.40.04).
The three changed translation units compile with HGCROC decoding enabled and
`-Werror=vla -Werror=mismatched-new-delete`. `git diff --check` passes.
Both versions of libLFHCAL were linked using the current upstream sources and ROOT dictionary.

## Actual fitter replay

The unmodified compiled `TileSpectra::FitMipHG` and `FitMipLG` implementations were called in
separate before/after processes. Both processes used the same histogram contents, stored errors,
previous calibration tables, SPS SumV2 mapping, mean active-channel MIP seed, and random seed.
The preserved nonfinite errors in the uploaded histogram bundle were not changed.
The test subclasses TileSpectra only to inspect the protected TF1 members, including rejected fits.

- 40 real SPS spectra: B1 R5, B2 R8, E1 R5, E2 R5, from both legacy/adaptive event selections.
- Four synthetic CAEN spectra: HG and LG, each with and without improved/pedestal fitting.
- All 44 results match exactly: acceptance, parameters, errors, fit ranges, chi-square/NDF,
  output buffers, and updated calibration values.
- 42 accepted, 2 rejected in each version. All four synthetic CAEN cases accepted; both
  seven-parameter pedestal-fit cases exercised.

The identical result file is included once as `fits.json`.

Input histograms.root SHA-256: `2503b07581ddd6098e2e184bf2676665d5078ec83cb766b79a3edda860903552`

Before/after fits.json SHA-256: `f7953858c1fa49442376387ffe0240c0fe32fc1ca1c593a1090d726ffa1720b7`

Example replay (run separately for each library):

```sh
python3 compare_fit_results.py --library /path/to/libLFHCAL.so \
  --headers /path/to/NewStructure \
  --bundle /path/to/fit-range-study-inputs-20261001-v2 \
  --out /path/to/results.json
```

This compares upstream before/after cleanup. It does not assert that the newer upstream
physics code reproduces every historical calibration value.

## Early-return buffer lifetime

`early_return_buffers.cc` calls the actual fitters for:

- 1,000 HG low signal/background rejections;
- 1,000 LG dead-channel rejections;
- 32 empty HG fits, exercising rejection after parameter-buffer allocation.

All return assertions pass in both versions. AddressSanitizer reports no access errors
with leak detection disabled. LeakSanitizer itself cannot inspect process threads in this
execution environment and was not usable for a leak verdict.

A separate executable built with `-DTRACK_FIT_ARRAYS -rdynamic -ldl` intercepts array allocation
and deletion, attributing allocations by the calling FitMipHG/FitMipLG symbol via dladdr:

| Version | Unreleased fit arrays | Bytes |
| --- | ---: | ---: |
| Before | 2,128 | 37,888 |
| After | 0 | 0 |

The allocation tracer deliberately returns exit 2 when outstanding fit arrays remain;
the before executable therefore exits 2 and the after executable exits 0.
These figures concern the fit buffers, not all ROOT allocations.

## Still pending

A full before/after Convert and DataPrep replay at BNL, including event/histogram comparison,
has not been run. Keep the PR draft pending production validation. The histogram-pointer
vector changes have compile coverage but have not been exercised through the full analysis pipeline.

## April PS E1 conversion sizes

The current April PS E1 recipe converts pedestal Run287 and muon Runs288–291 without an event limit.
The reported sizes (44M pedestal, about 1.2–1.4G per muon ROOT, 4.7G merged) alone do not
prove completeness. These April PS conversions are distinct from the May SPS spectra used above.
`check_conversion_counts.py` reads Data tree entry counts and hNEvents counters, flags unreadable
or recovered files, and checks that the merge equals the sum of its muon inputs. An existing final
extra TdataOut->Fill() explains a possible +1 between tree entries and the decoder counter.
Counters are a screening check, not independent proof that all raw packets were processed.
