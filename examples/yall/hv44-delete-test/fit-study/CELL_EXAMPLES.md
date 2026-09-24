# Collect representative run-194 spectra on BNL

Copy `export_cell_examples.C` and `collect_cell_examples.sh` together to BNL.
They need ROOT in the existing EIC environment; no build or package installation
is needed. The provided tools archive contains both files.

In the existing BNL tcsh session (where `EIC_SHELL` is already defined), after
unpacking `cell-examples-tools.tgz` in the current directory:

```tcsh
set TEST = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tbana-delete-test"
set W = "/gpfs01/star/scratch/$USER/lfhcal/hv44-delete-test"
bash ./collect_cell_examples.sh "$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
  "$W/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_Hists.root" \
  "$W/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_calib.txt" "$W"
```

This reads the existing refine2 histograms and calibration and creates a unique
`cell-examples-XXXXXX` directory and matching `.tgz`/`.tgz.sha256` files under W.
The script prints the exact two files to transfer to the Mac. Inputs and code
are hashed before export and verified afterward; logs, command, status and
elapsed whole seconds are preserved. Failures keep partial output and do not
produce the archive. Run from any shell by invoking the script with `bash`.

The export contains:

- `entries.csv`: every calibration cell's ID, geometry, BC flag, histogram
  presence, GetEntries, in-axis integral, underflow/overflow and selection reason.
  Missing histograms have explicit NaN counts; present empty histograms have zero.
- `examples.root`: unchanged TH1 copies as `cell<ID>`, plus available
  `hmipTriggers`, `hMipTriggXY`, `hMipTriggXYZ` maps and `source_context` metadata.
- `calibration.txt`: exact copy of the supplied calibration table.
- `summary.txt`: population/missing counts, entry-count order statistics, median,
  and selected cell IDs.

Examples are cell 903 (if present), p10, p50, p90 and the maximum by entry count,
deduplicated. The comparison population is all present histograms with BC>=2,
including zero-entry cells and cells whose calibration fit failed. Sorting uses
entry count then cell ID; representative ranks use round(p*(N-1)). The reported
median averages the two central counts when N is even, so its value can differ
from the selected p50 example. No low-count cells are removed to select examples.
BC<2 masked cells and missing histograms are reported separately from this
population; a missing histogram does not silently become zero.

Counts are entries in the selected per-cell MIP spectrum, not total run events.
No refilling, rebinning, fitting, calibration updates, or error replacement is
performed. Imported errors/NaNs and any attached objects are preserved; stored
fit callbacks are not guaranteed evaluable after loading. The extractor reads
only ROOT-standard objects and does not need the production dictionaries.

Validation on Mac ROOT 6.40.04: compiled CTest covers representative selection,
masked/missing/zero cells, ties, median, NaNs, axes, errors, underflow/overflow,
source preservation and overwrite refusal. The interpreted ROOT macro was also
run against an original-layout fixture made from the actual transferred cell903
histogram. That smoke test is not an all-cell BNL run or evidence of its typical
statistics. BNL execution still requires the original all-cell Hists file.
