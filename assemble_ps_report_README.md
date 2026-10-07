# PS-2026 calibration summaries

Run `assemble_ps_report.py` at BNL on the completed PS calibration work directory.
It packages existing PNGs and calibration text; it does not run ROOT or refit data.

```console
python3 -m pip install --user reportlab
python3 assemble_ps_report.py --root /gpfs01/star/scratch/pnord/lfhcal/ps-sps-calibration-20261006 --out /gpfs01/star/scratch/pnord/lfhcal/ps-summaries-20261007 --pdf
```

The output directory must be new. The default selects all 17 PS sets; use
`--sets ps-b1 ps-b2` to package a subset. Without `--pdf`, only the HTML collection,
PNGs, text constants, inventories and ZIP are made.

## Summary template

Each `SummaryPS_A1.pdf`, etc., follows the plot selection and page order of
F. Bock's 27-page `SummarySetB.pdf`. This is the plot summary, not her separate
SPS analysis-status presentation. Each original PNG fills its PDF page, retaining
its aspect ratio and fit overlays. No title pages or captions are inserted.
The PDF outline provides set and plot labels. The combined
`ps-2026-r5-report.pdf` contains these same pages in set order (459 for all sets).

| Pages | R5 plots |
| --- | --- |
| 1-6 | HG FWHM, Gaussian width, Landau MPV, Landau width, peak, chi-square/ndf |
| 7-14 | MIP spectra with fits, layers 0-7 |
| 15-19 | XY trigger counts, per-channel trigger counts, SNR, noise-region S/B, signal-region S/B |
| 20-27 | Trigger primitives, layers 0-7 |

The fixed order is `SUMMARY_PAGES` in the script. Files are selected by exact
basename within each set's `plots/refine5` directory. An absent map or duplicate
matching filename stops packaging rather than using an arbitrary substitute.
ROOT can omit layer panels when all channels are masked. An absent layer panel
produces a clearly labelled placeholder at its reference page number, a console
warning, and an inventory entry. The assembler does not infer why it is absent.

These are PS results from adaptive HG fitting with the original fit boundary.
Matching the report format does not make the fitter or the numerical results
identical to the SPS reference. The old `legacy-original` campaign names do not
describe the HG fitter actually identified in this deployment.

## Other output

- `index.html`: set links, run/pedestal notes, complete earlier-stage PNG collections.
- `summary-pages.csv`: exact per-set PDF page-to-input mapping, including missing panels.
- `manifest.json` and `plot-inventory.csv`: source paths and complete PNG inventory.
- Final and intermediate calibration text files alongside the images.
- A ZIP next to the report directory for downloading the complete collection.

All PNGs remain available in HTML, including R5 plots not selected for the
27-page PDF. The source-recipe notes are historical association/recipe caveats,
not new conclusions inferred from the current plots. No flow charts are added.

Validation used rasterized pages of the supplied SPS reference as local test
inputs: page order, per-set/combined page counts, rendering without cropping,
missing-layer placeholders and ambiguous/missing-map rejection were checked.
The real PS input plots remain at BNL and are read when the command is run there.
