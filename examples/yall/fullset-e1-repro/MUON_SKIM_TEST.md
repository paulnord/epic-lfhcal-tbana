# FullSetE_1 with `DataPrep -M`

This experiment uses the same complete pre-skim adaptive E1 MIP event file as
the corrected `-X` test. Only the selection operation changes: `-M` invokes
`SaveMuonTriggersOnly()`, retaining tiles whose stored `LocalTriggerBit == 1`.
All five refinement commands, fit settings and final copies match the `-X`
recipe. No production C++ code changes or rebuild are required for this recipe.

`-M` writes every input event record, including events that become empty after
tile removal. For this E1 input, expect 698,044 event records, rather than the
692,273 accepted by `-X`. The selected tile count must be measured. This uses
the flags already stored by the initial MIP step; tiles rejected here cannot
be recovered by later refinements.

## Launch alongside the running `-X` campaign

Use the BNL host tcsh shell with the existing LFHCAL/EIC environment and tested
DataPrep build. Update the adaptive checkout with these workflow files:

```tcsh
cd "$LFHCAL_REPO"
git switch codex/yall-adaptive-mip && git pull --ff-only
```

Use current yall-run `main` with `%preflight` support. The following keeps the
existing `C` and `LFHCAL_WORK` variables pointing to the `-X` campaign. New
variables `CM` and `LFHCAL_WORK_M` identify the `-M` run.

```tcsh
setenv LFHCAL_PREVIOUS "/gpfs01/star/scratch/pnord/lfhcal/e1-host-setup-7FvPNa/fullset-e1-repro"
setenv LFHCAL_WORK_M `mktemp -d /gpfs01/star/scratch/pnord/lfhcal/e1-muon-only-XXXXXX`
cd "$LFHCAL_REPO/examples/yall/fullset-e1-repro"
env LFHCAL_WORK="$LFHCAL_WORK_M" yall-run validate Yallfile.after-mip-muon && \
env LFHCAL_WORK="$LFHCAL_WORK_M" yall-run plan Yallfile.after-mip-muon
```

Check that the plan has one host preflight and six batch jobs: `select-e1`,
then `refine1-e1` through `refine5-e1`. Stop if validation or creation fails.

```tcsh
set CM = `env LFHCAL_WORK="$LFHCAL_WORK_M" yall-run create Yallfile.after-mip-muon --campaigns-dir "$LFHCAL_WORK_M/campaigns"`
yall-run start "$CM"
yall-run status "$CM"
echo "Muon-only results: $LFHCAL_WORK_M"
echo "Muon-only campaign: $CM"
```

Do not run `prepare_after_mip.py` separately: `%preflight` runs its
`--muon-only` mode during creation, on the host outside the EIC wrapper. It
checks inputs and prepares the fresh output directories and comparison files.
It refuses to reuse an already-prepared result directory. Original event
trees remain in place and are read only; small comparison inputs are copied.

## Selection audit and final comparison

The selection job runs `compare_muon_skim.C` against the pre-skim input after
`DataPrep -M` succeeds. The audit requires unchanged event identity/order and
metadata, and exactly the original trigger-bit-1 tiles in their original order
with unchanged payloads. Empty events are valid. JSON and per-cell CSV reports
are written under `skim-check/`; refinements depend on this audit passing.
Existing audit reports are never overwritten: preserve/move them before
retrying selection after it has produced a report.

```tcsh
cat "$LFHCAL_WORK_M/fullset-e1-repro/skim-check/selection.json"
```

After completion, compare with the earlier adaptive result using the original
buggy `-X` skim:

```tcsh
python3 "$LFHCAL_REPO/examples/yall/compare_fullset.py" \
    --set-name FullSetE_1 --work "$LFHCAL_WORK_M/fullset-e1-repro" \
    --reference "$LFHCAL_WORK_M/fullset-e1-repro/baseline/calib_Final_Muon_FullSetE_1_calib.txt" \
    --out "$LFHCAL_WORK_M/fullset-e1-repro/report-vs-old-X" --no-pdf
```

Once the corrected `-X` run also finishes, compare directly with it:

```tcsh
python3 "$LFHCAL_REPO/examples/yall/compare_fullset.py" \
    --set-name FullSetE_1 --work "$LFHCAL_WORK_M/fullset-e1-repro" \
    --reference "/gpfs01/star/scratch/pnord/lfhcal/e1-skim-fixed-y8Dumx/fullset-e1-repro/final/calib_Final_Muon_FullSetE_1_calib.txt" \
    --out "$LFHCAL_WORK_M/fullset-e1-repro/report-vs-fixed-X" --no-pdf
```

Preserve histograms and logs from both campaigns. The comparisons measure the
calibration effect of the different selection; neither establishes that all
fits are physically good. `GetImprovedScaling()` still applies its own local
muon-trigger criterion before filling fitted spectra.

## Collect both completed runs for transfer

From the tcsh terminal where `C` is the corrected `-X` campaign and `CM` is
the `-M` campaign:

```tcsh
cd "$LFHCAL_REPO"
python3 examples/yall/collect_e1_comparison.py "$C" "$CM"
```

This uses only Python's standard library, with no shell switch or pasted
multiline program. It prints one archive and its SHA-256 file to transfer.
The archive includes both campaigns' logs and metadata, all stage histograms,
calibration text, selection audits, existing reports, setup metadata and the
packaging checkout's revision/status/diff. Event-tree ROOT files and the
`plots` directory are excluded. Inputs remain unchanged; every invocation
creates a fresh output directory alongside the work directories. Missing
refinement histograms, calibration text, final calibration or selection audit
stop collection before creating an archive.
The campaign container may have any name. If the supplied path is absent,
the collector accepts a unique directory with the exact same campaign name
under another container in the same work directory and prints the resolved
path; missing or ambiguous matches remain errors.
