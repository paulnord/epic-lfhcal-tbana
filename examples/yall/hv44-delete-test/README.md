# 44 V delete[] regression test

This is an isolated regression test for the array-deallocation fix in
`TileSpectra.cc`.

It reproduces one published HV-scan calibration only:

- pedestal run 188
- muon run 194 (44 V)
- reference: `calibrations/TB2026/calib_SPS-H2_HVScan_44V.txt`

Use this from a separate Git worktree so running production campaigns continue
to use their existing checkout and build tree.

After the campaign completes, compare numerically with:

```tcsh
python3 ../fullset-g1-repro/compare_and_report.py \
    --work "$LFHCAL_WORK/hv44-delete-test" \
    --reference ../../../calibrations/TB2026/calib_SPS-H2_HVScan_44V.txt \
    --set-name HVScan_44V \
    --no-pdf
```
