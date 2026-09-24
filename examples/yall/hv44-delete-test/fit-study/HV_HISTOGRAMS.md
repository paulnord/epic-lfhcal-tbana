# Bring the complete HV histograms to the Mac

The first comparison uses the existing **refine2** stage at all nine HV points:
201 (42 V), 202 (42.5 V), 195 (43 V), 196 (43.5 V), 194 (44 V),
197 (44.5 V), 198 (45 V), 199 (45.5 V), and 200 (46 V).

For each run the collector copies the complete original ROOT histogram file,
the refine1 calibration, and the refine2 calibration. It preserves the campaign's
relative directory layout and records source paths and SHA-256 hashes. It does
not require ROOT, run event processing, or change any source files. All requested
inputs must exist; missing runs are an error, not silently omitted data.

On BNL, with `collect_hv_histograms.py` in the current directory:

```sh
python3 collect_hv_histograms.py \
  --work /gpfs01/star/scratch/pnord/lfhcal/hvscan-repro \
  --out-parent /gpfs01/star/scratch/pnord/lfhcal
```

The script prints the new archive and checksum paths. Transfer both files into a
new directory under the Mac workspace's `local-data/`, verify the checksum there,
and extract the archive without overwriting earlier imports. The source files
remain separately identifiable from the `hv44-delete-test` regression campaign.
If only that campaign is available, an explicitly limited collection is:

```sh
python3 collect_hv_histograms.py \
  --work /gpfs01/star/scratch/pnord/lfhcal/hv44-delete-test \
  --out-parent /gpfs01/star/scratch/pnord/lfhcal \
  --runs 194
```

After importing, the observational analysis reads the extracted directory:

```sh
python3 analyze_hv_histograms.py --work /path/to/extracted/campaign \
  --out /Users/pnord/Work/lfhcal-cell903/local-results/hvscan-inspection-NEW
```

For an explicitly limited run set, pass the same `--runs` list to the analyzer.
The output directory must be new. The analyzer requires the existing Mac PyROOT
environment and writes per-cell counts, missing/zero distinctions, calibration
fields, input hashes, summaries, and plots. It performs no refits and applies no
minimum-count cut to the analysis population. Threshold counts are descriptive.

## Interpretation limits

- Counts are selected per-cell MIP histogram entries, not total run events or
  directly comparable exposure-normalized fluxes. Selection uses previous
  calibration results and can vary between HV points and refinement stages.
- All nine runs have table position (0, 0) recorded. This does not prove their
  beam profiles or exposures were identical.
- A campaign name does not establish the build revision that produced its ROOT
  files. Keep `hvscan-repro` and `hv44-delete-test` provenance separate. Existing
  checks of the 44 V regression do not establish equivalence at every voltage.
- FullSetC_2 combines several beam positions and uses a different bad-channel
  map and ToA offsets; it is a separate calibration population.
- Stored calibration values and stored TF1 parameters are historical outputs.
  A readable function or finite scale is not a new validation of its fit.
- The standalone fitter's cell903 defaults must not be applied to arbitrary
  cells: target ID, pedestal, preceding calibration, segment size, and Vov all
  need explicit routing. The first analysis does not change those assumptions.
