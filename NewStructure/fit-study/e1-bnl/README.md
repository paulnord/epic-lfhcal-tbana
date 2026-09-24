# E1 BNL test of the width-scaled legacy Langau grid

This small yall-run campaign replays **only `refine5`** with `DataPrep` built from
`codex/legacy-langau-width-grid`. It consumes the selected E1 ROOT file and
`refine4` calibration from the archived legacy `fullset-e1-repro` run. A second,
short job compares the resulting fit functions against the archive's existing
`refine5` result. No raw conversion, pedestal, transfer, MIP pass, or previous
refinement is submitted. The archive is read-only; the new outputs and campaign
record stay together in a fresh directory under `$LFHCAL_WORK`.

The fitting job uses the same `DataPrep -x -a -f -d 1 -S` command and run
database as the original E1 `refine5` task. The comparison reports saved HG fit
counts, median chi-square/ndf, gained and lost fits, the largest changes, and
full fit parameters for cells 896 and 903. It also verifies that both text
calibrations contain 384 cell records. Completion means the workflow and
structural checks passed; scientific acceptance remains a separate judgment.

## Run at BNL with tcsh

Paste these one-line commands individually. This uses a separate checkout, so
your current adaptive branch and build are untouched. The E1 source path is
the PWG archive used for the earlier `fullset-e1-repro` copy. Check that the
required archived files exist before creating the campaign.

```tcsh
cd "$HOME/my_eic_work_with_LFHCAL"
source activate.tcsh
set REPO = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-legacy-width-grid"
setenv EIC_SHELL "$HOME/my_eic_work_with_LFHCAL/eic-shell"
git clone --recurse-submodules --branch codex/legacy-langau-width-grid https://github.com/paulnord/epic-lfhcal-tbana.git "$REPO"
"$REPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" cmake -S "$REPO/NewStructure" -B "$REPO/NewStructure/build"
"$REPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" cmake --build "$REPO/NewStructure/build" --target DataPrep -j 4
setenv LFHCAL_E1_SOURCE "/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBanalysis/fullset-e1-repro"
ls -lh "$LFHCAL_E1_SOURCE/selected/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_FullSetE_1.root"
ls -lh "$LFHCAL_E1_SOURCE/refine4/rawHGCROC_wPedwMuon_wBC_Imp4R_Muon_FullSetE_1_calib.txt"
ls -lh "$LFHCAL_E1_SOURCE/refine5/rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_FullSetE_1_Hists.root"
setenv LFHCAL_E1_OUT "$LFHCAL_WORK/legacy-width-grid-e1-`date -u +%Y%m%dT%H%M%SZ`"
mkdir -p "$LFHCAL_E1_OUT"
cd "$REPO/NewStructure/fit-study/e1-bnl"
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_E1_OUT/campaigns"`
yall-run start "$C"
yall-run status "$C" -vv
```

`yall-run create` runs preflight to make the new output tree. The fit job
declares its ROOT, calibration, histogram, and plot outputs; the comparison
job produces `$LFHCAL_E1_OUT/comparison.json`. The campaign directory holds
the exact commands, inputs, outputs, logs, and attempt provenance.

After completion:

```tcsh
yall-run status "$C" -vv
cat "$LFHCAL_E1_OUT/comparison.json"
```

Start with cell 896. In the archived legacy result its Landau width was about
0.122 ADC, Gaussian sigma about 7.889 ADC, and chi-square/ndf about 223.
Cell 903 is a less pathological control: width about 2.59 ADC and
chi-square/ndf about 13.3. Review fit-count changes and large regressions in
addition to any improvement at 896.
