# Test the corrected event skim on FullSetE_1

Reuse the previous adaptive run's MIP event file. Run selection again, followed
by all five refinements with the same fitting options. This isolates the skim
correction from changes to conversion, pedestal extraction or initial MIP fits.
Existing BNL outputs are inputs only; all new results go to a fresh directory.

## Update and rebuild in the BNL host tcsh shell

Start outside the EIC container. The wrapper enters it for builds and jobs.

```tcsh
cd "$HOME/my_eic_work_with_LFHCAL"
source ./activate.tcsh
setenv LFHCAL_REPO "$LFHCAL_HOME/epic-lfhcal-adaptive-2f4bbd5"
cd "$LFHCAL_REPO"
git switch codex/yall-adaptive-mip && git pull --ff-only
git log -1 --oneline
```

Rebuild the executable and regression tests; stop if any command fails.

```tcsh
"$LFHCAL_REPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" cmake -S "$LFHCAL_REPO/NewStructure" -B "$LFHCAL_REPO/NewStructure/build" -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON && \
"$LFHCAL_REPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" cmake --build "$LFHCAL_REPO/NewStructure/build" -j2 --target DataPrep test_langau_numerics test_adaptive_mip test_adaptive_root_roundtrip test_hgcroc_skim && \
"$LFHCAL_REPO/tools/run-in-eic-shell.sh" "$EIC_SHELL" ctest --test-dir "$LFHCAL_REPO/NewStructure/build" --output-on-failure
```

Expect **8 tests passed**, including the three skim fixture/run/check tests.
Keep this checkout and build unchanged while the campaign runs.

## Prepare and submit

`LFHCAL_PREVIOUS` is the old **fullset-e1-repro** directory, not its parent.
Do not source `env.tcsh` after setting these variables; it resets paths.

```tcsh
setenv LFHCAL_PREVIOUS "/gpfs01/star/scratch/pnord/lfhcal/e1-host-setup-7FvPNa/fullset-e1-repro"
setenv LFHCAL_WORK `mktemp -d /gpfs01/star/scratch/pnord/lfhcal/e1-skim-fixed-XXXXXX`
cd "$LFHCAL_REPO/examples/yall/fullset-e1-repro"
python3 prepare_after_mip.py && \
yall-run validate Yallfile.after-mip && \
yall-run plan Yallfile.after-mip
```

Setup runs on the host. It checks required input files, creates directories,
copies the MIP histograms/calibration and previous final calibration for later
comparisons, and records paths, file sizes and copied-file hashes in
`$LFHCAL_WORK/after-mip-setup.json`. Large event trees are read in place.
It refuses an already-used result directory. Stop if setup or validation fails.

The plan should contain **six tasks**: `select-e1`, then `refine1-e1` through
`refine5-e1`. Final copies run inside refine5; there is no setup or final batch
job. Submit:

```tcsh
set C = `yall-run create Yallfile.after-mip --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C"
echo "Results: $LFHCAL_WORK"
echo "Campaign: $C"
```

## Inspect the skim comparison and calibration changes

After writing the corrected skim, the selection job runs `compare_skim.C`
against the old selected tree. Refinements proceed only if this comparison
passes. It checks event IDs/order, event metadata, retained-tile order and
payloads, and that no previously retained tile was lost. It also counts added
tiles per cell. This reads both selected trees, so selection will take longer
than the skim operation alone.

The audit refuses to overwrite existing `selection.json` or `selection.csv`.
If selection fails after writing reports, inspect and move those reports aside
before retrying, or use a fresh work directory.

Expected: the same **692,273 accepted events**, with leading tiles restored in
some events. The number of restored tiles and calibration impact must be
measured on BNL. Added tiles are not independently compared with the pre-skim
input by this audit; the synthetic regression test checks that full-event
preservation directly.

```tcsh
cat "$LFHCAL_WORK/fullset-e1-repro/skim-check/selection.json"
```

The accompanying `selection.csv` lists old/new tile counts and additions for
each cell. Once refine5 succeeds, compare with the **previous adaptive result
using the old skim**:

```tcsh
python3 "$LFHCAL_REPO/examples/yall/compare_fullset.py" \
    --set-name FullSetE_1 \
    --work "$LFHCAL_WORK/fullset-e1-repro" \
    --reference "$LFHCAL_WORK/fullset-e1-repro/baseline/calib_Final_Muon_FullSetE_1_calib.txt" \
    --out "$LFHCAL_WORK/fullset-e1-repro/report-vs-old-skim" --no-pdf
```

This comparison attributes downstream changes to rerunning selection and its
dependent refinements with the corrected skim, subject to platform/runtime
reproducibility. It does not establish that every resulting fit is physically
good. Preserve the per-stage histograms, calibrations and job logs for review.

## Local validation

`python3 examples/yall/test_fullset_e1_after_mip.py` (with yall-run available)
checks input isolation, host setup and unchanged refinement commands.
The comparator was checked with actual old/fixed synthetic DataPrep outputs:
eight unchanged events, 14 to 20 tiles, six restored. Reverse comparison,
changed energy, changed event ID and changed retained-tile order each fail.
Full E1 event trees are available on BNL, not in the Mac histogram archive.
