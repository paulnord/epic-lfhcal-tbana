# Late-jump spectra at BNL

This review reconstructs saved curves using the campaign's archived Legacy and
Adaptive evaluators. It does not rerun calibration or fit the histograms.

Default cases:

| Set | Cells | Reason |
| --- | --- | --- |
| B2 | 704, 579, 2562, 709 | New Adaptive R7 to R8 calibration jumps above 1% |
| B2 | 2118 | Remaining new Legacy jump above 1%; missing Adaptive fit pairs |
| B2 | 1287 | Largest old Legacy R8 jump; compare the new boundary |
| E1 | 196, 1348 | Two largest new Legacy R4 to R5 calibration jumps |
| B1 | 704, 1287 | Same detector cells as B2, with stable final steps |

B2 pages show R6, R7, R8. B1/E1 pages show R3, R4, R5. Each cell has four
three-panel pages: original/valley boundary crossed with Legacy/Adaptive. All
four pages for a cell share axes. Original bins, saved curves, and both fit
limits are shown. There are 40 PNGs and three PDF books for the default cases.

Run in tcsh:

```tcsh
set REPO = ~/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark
set RANGEWORK = /gpfs01/star/scratch/pnord/lfhcal/boundary-fullchains-20261002
git -C "$REPO" fetch origin codex/adaptive-langau-minimal && \
git -C "$REPO" show FETCH_HEAD:plot_boundary_cases.py > /tmp/plot_boundary_cases.py && \
git -C "$REPO" show FETCH_HEAD:plot_discrepant_spectra.py > /tmp/plot_discrepant_spectra.py && \
"$RANGEWORK/run-in-eic-shell.sh" ~/my_eic_work_with_LFHCAL/eic-shell \
  /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 \
  python3 /tmp/plot_boundary_cases.py --root "$RANGEWORK" --out "$RANGEWORK/interesting-cases"
```

Download `interesting-cases.zip` from that campaign. After extracting it, open
`index.html`. The ZIP also contains:

- `parameter-history.csv`: MIP and every refinement for the selected cells,
  including H, MPV, both widths, fit limits, new range-finder decisions, count
  fingerprints, and step changes. Step changes require both adjacent fits to
  have been saved. A carried-forward H is retained in the table but not treated
  as a successful fit. Original range-finder diagnostics are unavailable; its
  actual saved TF1 limits remain available.
- `histograms.root`: unmodified histograms and saved TF1 objects for the displayed
  stages, under `dataset/boundary/model/stage/cellID/{histogram,saved_fit}`.
- `manifest.json`: input report hashes, source hashes, ROOT version, individual
  histogram count fingerprints, sampling resolution, and any curve errors.

Each panel uses its own stage's histogram: the iterative calibration can change
the event selection. Shared axes do not imply identical histogram inputs.
The renderer samples archived evaluators using saved parameters, rather than
relying on a deserialized callback TF1 to evaluate itself. Missing saved fits
have no reconstructed curve. A sampling error is labeled and returns exit 2
after making the review bundle; it never substitutes a different evaluator.

Finite stored bin errors are displayed. Nonfinite errors are omitted and labeled;
they are not replaced with invented Poisson errors. The original error storage,
including NaNs, is preserved in the ROOT bundle. No histogram normalization,
rebinning, smoothing, or refitting is performed.

Original histogram directories come from the campaign's frozen reference map,
including the separate B2 R6-R8 extension. Saved parameters, fit ranges, and
original-bin counts are checked against their per-cell reports. Missing files,
changed frozen references, inconsistent reports, or the wrong ROOT version stop
the review. Existing output is preserved; use another `--out` to rerun.

`check_boundary_cases.py` tests reference resolution, missing-fit step gaps,
histogram/parameter/range checks, and nonfinite-error display behavior without
ROOT. These checks do not validate physical fits or ROOT rendering; those run
in the BNL EIC shell.
