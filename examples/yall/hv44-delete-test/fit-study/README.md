# Cell 903 isolated MIP-fit study

This small ROOT-only program isolates the unstable MIP fit seen for cell 903 in
the 44 V HV-scan calibration. It does **not** run the LFHCal event loop.

The input is one already-produced histogram. The program reproduces the
Landau-Gaussian convolution, fit-range rules, parameter starts/limits,
Minuit2/Migrad selection, and the production \`QRLMN0\` fit options used by
\`GetImprovedScaling\` / \`FitMipHG\`.

The defaults are specific to the observed run-194 case: cell 903, pedestal
sigma 0.581290, Vov 5.7 V, and the more-than-five-layers fit branch.

## Build in the EIC environment

\`\`\`tcsh
set STUDY = "$TEST/examples/yall/hv44-delete-test/fit-study"

"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    cmake -S "$STUDY" -B "$STUDY/build"

"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    cmake --build "$STUDY/build" -j2

set FIT903 = "$STUDY/build/fit_cell903"
\`\`\`

## Reproduce the two observed production fits

Use the refine2 histogram, which was verified bin-for-bin identical to the
refine3 histogram:

\`\`\`tcsh
set H903 = "$W/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_Hists.root"
set C1 = "$W/refine1/rawHGCROC_wPedwMuon_wBC_ImpR_194_calib.txt"
set C2 = "$W/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_calib.txt"

"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 \
    "$FIT903" "$H903" --calib "$C1" --calib "$C2" \
    | tee /tmp/cell903-two-seeds.csv
\`\`\`

The two rows should first reproduce the stored refine2/refine3 solutions. If
they do not, stop there: the standalone setup is still missing a production
detail.

## Scan the global average-MIP seed

Once the two known fits reproduce:

\`\`\`tcsh
"$TEST/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 \
    "$FIT903" "$H903" --scan 52.00 52.20 0.001 \
    > /tmp/cell903-scan.csv
\`\`\`

The CSV records fit range, start values, parameter limits, fitted parameters,
derived peak/FWHM, fit status, chi-square, and NDF.

The program also supports \`--fit-low\`, \`--fit-high\`, \`--start-mp\`,
\`--mp-low\`, and \`--mp-high\` so the fit window and MP seed can be varied
independently after the basin boundary is located. \`--fit-option QRLN0\` allows
a direct comparison with the production fit minus the \`M\` option.
