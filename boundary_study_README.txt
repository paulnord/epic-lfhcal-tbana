LFHCal boundary sensitivity follow-up

This test does not modify production calibrations. It uses the frozen original
histograms and the archived adaptive convolution implementation.

For each of 40 histograms, independently fit seven lower edges around the
sigma=2-bin smoothed-valley candidate: offsets -2,-1,-0.5,0,0.5,1,2 times
max(2 original bin widths, 5% of the observed smoothed peak). The primary
neighborhood is offsets -1..1; +/-2 is a stress test. Two additional trials
change the original upper edge by +/-10%, holding the candidate lower edge.
Both selected-histogram populations use the adaptive evaluator. There is no
best-of-fit selection. Smoothing only locates the valley; fitted bins are raw.

Retain production starts and parameter limits except area seed and upper limit,
which are recomputed from each fit window as in production. Use 1000 function
calls / 100 iterations, QRLMN0S, and fixed IMPROVE seed 12345. Preserve the input
ROOT file; in working clones only, nonfinite errors in empty bins are set to
zero. The prior baseline study found this did not materially change the fits.
Local ROOT is 6.40.00; extraction ROOT was 6.40.04. The central trial must match
the prior production-budget candidate within 1e-6 relative H. Observed maximum discrepancy is 1.7e-7 relative H
(0.000017%); a stricter initial 1e-9 check failed for one first-study fit.

The four histograms with no resolved valley are explicitly flagged. Their
neighborhood scans are diagnostics around the retained original edge, not
validation of the valley proposal. The peak scale falls back to the dataset
average only when no observed peak is available. No universal calibration
acceptance threshold is inferred from this selected sample.

New controls: pack_fit_range_controls.py exports 64 histograms for 32 new
run/cell cases. B1, E1 and E2 each contribute one previously unused cell per
layer. Both original fits must be saved, BC>=2, H inside the fit window and
legacy/adaptive H agreement within 1%. Choose the lower-median adaptive entry
count within each layer, ties by cell ID. B2 contributes the same eight cells
as B1 without screening B2 outcomes. All previously studied cell IDs are
excluded. This deliberately tests original-method agreement cases and is not
an unbiased detector sample. The selection and audit are frozen in
range-control-selection.json and embedded in the standalone exporter.

Run on BNL in tcsh:
set REPO = ~/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark
git -C "$REPO" fetch origin codex/adaptive-langau-minimal && \
git -C "$REPO" show FETCH_HEAD:pack_fit_range_controls.py > /tmp/pack_fit_range_controls.py && \
/gpfs01/star/scratch/pnord/lfhcal/adaptive-fullchains-20260928T223211Z/run-in-eic-shell.sh ~/my_eic_work_with_LFHCAL/eic-shell python3 /tmp/pack_fit_range_controls.py --out /gpfs01/star/scratch/pnord/lfhcal/fit-range-controls-20261002

Upload /gpfs01/star/scratch/pnord/lfhcal/fit-range-controls-20261002.zip.
Exporter opens campaign data read-only and refuses to overwrite an output.
No event data are included. Full downstream calibrated-response validation
requires a separate event-level calibration replay; it is not established by
these frozen-spectrum tests or by agreement between the two fitters.

Reproduce the current 360-fit test with run_fit_range_study.py and
 test_boundary_stability.py from the same GitHub branch:
python3 test_boundary_stability.py --bundle INPUT_BUNDLE --out boundary-b1 --datasets b1
python3 test_boundary_stability.py --bundle INPUT_BUNDLE --out boundary-other --datasets b2 e1 e2
The analyzer additionally expects the prior production-candidate and scan-b1,
scan-b2, scan-e result directories beside it. See the first study README.
