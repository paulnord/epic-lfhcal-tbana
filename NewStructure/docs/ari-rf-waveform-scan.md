# Ari RF waveform scan

`HGCROCStudy -w` now writes per-cell waveform peak amplitude, peak time, FWHM,
and extraction status histograms to its histogram ROOT file. The measurements
use the mean waveform profile stored by `TileSpectra`.

The default FWHM definition matches `RF_Scans_Waveform.C`: the peak search ends
at `FindBin(200 ns)`, peak time is the maximum-bin center, and FWHM is the
difference between the centers of the first at-or-below-half-height bins on
each side. `TileSpectra::MeasureWaveform(..., true)` is a separate interpolated
crossing mode; it is not used by the RF scan plots.

Missing or non-positive peaks and missing crossings have explicit status codes.
Peak amplitude/time remain available when only the width is undefined; an
undefined width is `NaN`, not zero.

Run the RF comparison with the usual two-file input list (calibration ROOT file,
then histogram ROOT file on each line), the May 2026 H2 run list, and `-A`:

```console
./CompareWaveform -A -I rf_inputs.txt \
  -r ../configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv \
  -o ari_rf_comparison.root -O ari_rf_plots -f
```

The `-A` mode uses Ari's 64 RF-scan cells and produces:

- `AriRF_WaveformMeasurementsMain.*`: main-distribution view with IQR boxes,
  median lines, Tukey whiskers and open-diamond outliers. Edge arrows count
  actual off-scale values separately above/below each RF setting.
- `AriRF_WaveformMeasurements.*`: full-range companion with every valid value;
  the original ROOT canvas key and `AllChannels` graph names are retained.
- `AriRF_WaveformSummary.*`: mean with channel-to-channel standard deviation,
  plus median. The error bars are spread across channels, not uncertainty on
  the mean.
- `AriRF_WaveformStatus.*`: valid/invalid extraction counts and boundary-peak
  counts for each RF setting.

The comparison ROOT file also stores the summary graphs and status histogram.

## Display conventions

Quartiles use the original unbinned linear `q*(n-1)` interpolation. Whiskers end
at the furthest observed values inside `[Q1 - 1.5 IQR, Q3 + 1.5 IQR]`, including
equality, rather than at the fences. All points keep deterministic display-only
jitter. Open diamonds identify statistical outliers, **not rejected channels**.

Each metric's main axis encloses every setting's box and observed whiskers,
with 8% lower/12% upper padding. Amplitude/FWHM start at zero when nonnegative;
negative data are never zero-clamped. Sparse interpolated quartiles remain on
scale. If this does not produce a useful narrower range, no extra crop is made.
Arrows indicate counts, not relocated values. The full companion shows their
actual positions. No measurements, masks, means, sample SDs or medians change.

FWHM coverage is displayed as extracted widths per 64 selected cells. Missing
widths remain missing, not zero. A valid extraction or an in-fence point is not
automatically a physically good waveform. Width distributions are conditional
on extraction success, not complete all-channel detector performance.

Custom ROOT primitives preserve exact unbinned quartiles; native histogram
CANDLE plotting would introduce bin-width-dependent quantiles.

## BNL: one isolated plot-only job

Reuse an existing two-column `rf_inputs.txt` pointing to completed calibration
and waveform histogram files. Do not rerun the raw-data or calibration campaign.
From **tcsh outside eic-shell**, use a separate checkout and a fresh output path:

```tcsh
set repo = "$HOME/ari-rf-plots-`date -u +%Y%m%dT%H%M%SZ`"
git clone --branch ari-waveform-rf-plots --single-branch https://github.com/paulnord/epic-lfhcal-tbana.git "$repo"
set inputs = "/absolute/path/to/completed/campaign/rf_inputs.txt"
set out = "/gpfs01/star/scratch/pnord/ari-rf-plot-`date -u +%Y%m%dT%H%M%SZ`"
python3 "$repo/NewStructure/scripts/prepare_ari_rf_plot_only.py" --inputs "$inputs" --output "$out" --eic-shell /star/u/pnord/bin/eic-shell
condor_submit "$out/job.sub"
```

The preparer only checks paths and writes one job; it does not submit it. The
job refuses login-host execution, verifies the checkout/head and input size/mtime,
builds `CompareWaveform` plus its focused tests inside eic-shell, runs those tests,
then reads the old inputs and writes new ROOT/PDF outputs. It does not use `-f`
or modify an existing campaign. A failed/partial attempt needs a new output path.
Outputs are under `$out/plots`; inspect `$out/job.out`, `$out/job.err` and the
Condor completion status. The decoder is not needed for this plotting-only build.

## Focused checks

```sh
cmake --build build --target CompareWaveform test_waveform_measurement test_ari_box_plot -j2
ctest --test-dir build --output-on-failure -R '^(waveform_measurement|ari_box_plot)$'
python3 -m unittest discover -s Tests -p test_prepare_ari_rf_plot_only.py -v
```

The box/range checks remain active in Release builds. They cover inclusive
fences, zero IQR, singleton/empty input, sparse quartiles, both off-scale tails,
exact axis edges and input preservation. These checks do not establish physical
quality of every waveform or agreement with an independently selected spreadsheet.
