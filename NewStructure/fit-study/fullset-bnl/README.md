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


To inspect every fit gained or lost against both the historical legacy archive
and the adaptive production, run the three-way audit inside the EIC container:

```tcsh
set REPO = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-legacy-width-grid"
set LEGACY_ROOT = "/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBanalysis"
set AUDIT = "$LFHCAL_FULLSET_OUT/legacy-adaptive-adjusted.json"
"$REPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    python3 compare_legacy_archive.py \
    --legacy-root "$LEGACY_ROOT" \
    --adaptive-root "$LFHCAL_WORK" \
    --candidate-root "$LFHCAL_FULLSET_OUT" \
    --out "$AUDIT"
```

The terminal output gives the three fit-presence flags. The JSON file also
records each available fit's parameters and each method's stored calibration.
Historical legacy inputs differ upstream, so the legacy comparison is
descriptive rather than a controlled same-input replay.
