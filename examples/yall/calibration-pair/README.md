# calibration-pair example

This is a small teaching/template workflow. The repository does **not** include the ROOT input files named in the `Yallfile`.

The example expects two pre-existing converted HGCROC ROOT files in this directory:

- `pedestal-input.root`: a pedestal run
- `mip-input.root`: a MIP/muon run

For TB2026, runs **296/298** are a natural example pedestal/MIP pair. If you already have full converted files for those runs, you can link or copy them here using the generic names above.

The `-L 1000` limits make this useful for exercising the workflow wiring, but 1000 events may not populate the MIP histograms well enough for a stable scaling fit. Treat this as a syntax/example workflow, not a physics-validation test. For a runnable local smoke test using the shared raw data, use `../lfhcal-simple` instead.
