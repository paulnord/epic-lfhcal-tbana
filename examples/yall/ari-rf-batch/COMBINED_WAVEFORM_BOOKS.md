# Native combined waveform books

Build `CombineWaveformBooks` with the normal NewStructure CMake build. This is a
standalone **display-only C++/ROOT** executable. It reads existing mean TProfiles
and the per-run `WaveformGrid_RunN_Measurements.csv` outputs. It does not process
events, fit, call `MeasureWaveform`, infer missing boundaries, or modify inputs.

```
./build/CombineWaveformBooks inputs.csv \
  configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv \
  /path/to/new/output/AllScans layer
```

The last argument is `layer` (default), `robust`, or `global`. The normalized book
always divides each displayed clone by its saved peak. The unnormalized book uses
the selected scale policy, with the same geometry and clipping indicators as the
native per-run grid. Original ROOT profiles and saved measurements are unchanged.

The executable produces exactly two books, each **26 pages**, with no title pages:
`AllScans_Unnormalized.pdf` and `AllScans_Normalized.pdf`. It draws one selected
view for every scan/run entry; it does **not** concatenate the four-view per-run
Original/Annotated PDFs. Both combined books include measurement guides.

## Input manifest

CSV header is exactly `run,profile_root,measurements_csv`, followed by one row per
run. Paths may be absolute or relative to the manifest directory; CSV quoting is
supported. Supply all 23 unique runs:

298, 300, 302, 304, 306, 310, 329, 333, 335, 337, 339, 341, 343, 345,
347, 349, 351, 353, 355, 357, 359, 361, 363.

For example, a row can be:

```
302,products/waveform/calibratedHGCROC_wave_Run_302_Hists.root,products/plots/waveform/Run302/WaveformGrid_Run302_Measurements.csv
```

Use the files from the same successful production attempt. Do not substitute the
summary-only `measurements.csv` from `plot_all_scans.py`: it lacks the saved left
and right crossing/bin values needed by the annotation renderer. No real-data
manifest is shipped because the production files are not present in this checkout.
All inputs are checked before either book is opened. Existing outputs are refused.
Missing runs/cells, duplicate inputs/cells, invalid flags/values, changed run
settings, unreadable/recovered ROOT files, and disagreement between CSV values and
saved ROOT summary histograms cause failure. Saved status histograms use status+1.
The ROOT keys are `IndividualCells/waveform1DfullCellIDN` and the four existing
`hWaveform*VsCellID` summary histograms. Crossings must be saved bin centers, matching
this annotation producer's no-interpolation convention.

## Scan provenance and order

The definitions match `plot_all_scans.py` (`EXPECTED`, `OPTIONAL_RF`, `GROUPS`) and
`prepare_other_scans.py`, and every run's four settings are checked against the
provided run database. RF uses the documented **nominal/provisional** H2GCROC3B
relation R = 80 / RF-code kOhm; this does not establish the installed chip revision.
Pages are grouped RF (blue), CC (orange), CF (green), CFComp (purple), then sorted
by increasing scan value, using run number only to break equal-value ties:

- RF: 345,343,341,339,337,335,298,333,329,310,306,304,302,300 (14).
- CC: 353,347,298,349,351 (5).
- CF: 361,355,363,298 (4; independent CF5 repeats retained).
- CFComp: 355,357,359 (3).

Run302 is nominal R=40 kOhm; Run300 is R=80 kOhm. A large colored header carries
the scan setting. Run298 and Run355 deliberately appear in multiple scan groups,
while their inputs are read only once. This produces the requested 26-page inventory using the established scan groups,
drawn natively rather than by PDF postprocessing.

`ctest -R waveform_books --output-on-failure` tests ordering, strict parsing,
complete synthetic 26+26-page rendering, saved values, refusal to overwrite, and
rejection of mismatched amplitudes, peak bins, and status flags.
Synthetic output is retained in a reported temporary directory for visual QA.
