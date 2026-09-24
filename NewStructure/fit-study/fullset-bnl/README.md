# Full-production BNL refine5 replay

This campaign tests the width-scaled legacy Langau grid across all twelve
completed adaptive FullSet productions. It begins at `refine5`, reading each
existing selected ROOT file and `refine4` calibration in place. It does not
rerun conversion, pedestal subtraction, MIP selection, or refinements 1--4,
and it does not copy their large data files.

The twelve `refine5` jobs run independently. Each has a dependent comparison
job that measures saved-fit counts, gained and lost fits, chi-square changes,
and calibration changes against the existing adaptive `refine5` result. A
final summary job combines all comparisons into `summary.json`.

At BNL, update the existing checkout and verify all required inputs:

```tcsh
cd "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-legacy-width-grid"
git pull --ff-only origin codex/legacy-langau-width-grid
cd NewStructure/fit-study/fullset-bnl
python3 check_inputs.py "$LFHCAL_WORK"
```

Every line should say `READY`. Then create a fresh output directory and submit
the campaign:

```tcsh
setenv LFHCAL_FULLSET_OUT "$LFHCAL_WORK/legacy-width-grid-fullset-`date -u +%Y%m%dT%H%M%SZ`"
yall-run validate
yall-run plan
set FULLCAM = `yall-run create --campaigns-dir "$LFHCAL_FULLSET_OUT/campaigns"`
yall-run start "$FULLCAM"
yall-run status "$FULLCAM" -vv
```

After all 25 tasks complete, inspect the aggregate comparison:

```tcsh
cat "$LFHCAL_FULLSET_OUT/summary.json"
```

The input trees remain untouched. The new ROOT, calibration, histogram, plot,
comparison, and provenance files all remain under `LFHCAL_FULLSET_OUT`.
