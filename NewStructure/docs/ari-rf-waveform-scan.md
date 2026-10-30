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

- `AriRF_WaveformMeasurements.*`: every valid channel point with an IQR box,
  median, and full-valid-range whiskers.
- `AriRF_WaveformSummary.*`: mean with channel-to-channel standard deviation,
  plus median. The error bars are spread across channels, not uncertainty on
  the mean.
- `AriRF_WaveformStatus.*`: valid/invalid extraction counts and boundary-peak
  counts for each RF setting.

The comparison ROOT file also stores the summary graphs and status histogram.
