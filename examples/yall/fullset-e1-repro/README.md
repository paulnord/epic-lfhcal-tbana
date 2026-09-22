# FullSetE_1 reproduction

This example runs the SPS H2 `FullSetE_1` merged-muon calibration chain
from raw TB2026 data using Yall and HTCondor, for comparison with the
published calibration. It uses the skimmed-event refinement path.

Pedestal: `372`

Muon runs, in Fredi's merge order:

```text
373 374 375 376 377 378
```

The merged input is `Muon_FullSetE_1`. This set uses the V2 summing-board
mapping, the shared FullSetA-F bad-channel map, and
`configs/TB2026/ToAOffsets_TBSPS2026_FullSetE.csv`.

The `select-e1` task explicitly runs `DataPrep -X`, which invokes
`Analyses::SkimHGCROCData()`. All refinements consume that selected event file.
The corrected skim retains the entire event if any tile triggers; older builds
could remove tiles preceding the first trigger. See
[event-skim behavior and regression test](../../../NewStructure/HGCROC_EVENT_SKIM.md).
After updating this code, rebuild DataPrep and use a fresh work directory for
selection and its dependent refinements. Existing selected files retain the
old selection behavior.

To test the correction with the existing adaptive E1 data, follow the
[BNL restart-after-MIP instructions](SKIM_RETEST.md). This runs six jobs in a
fresh directory and compares the corrected skim with the previous selection.
For the separate muon-triggered-tile (`-M`) experiment, use
[the E1 muon-only instructions](MUON_SKIM_TEST.md).

Published reference:

```text
calibrations/TB2026/calib_SPS-H2_FullSetE_1.txt
```

## Download raw files

```tcsh
tcsh download_raw.tcsh
```

The helper uses `$LFHCAL_DATA` when set, otherwise Paul's standard TB2026 PWG
directory. Existing nonempty files are skipped and new downloads go through a
temporary `.part` file.

## Run at BNL

```tcsh
cd "$LFHCAL_REPO/examples/yall/fullset-e1-repro"
source env.tcsh
yall-run validate
yall-run plan
set C = `yall-run create --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C"
```

Results go under `$LFHCAL_WORK/fullset-e1-repro/`. The final text
calibration is
`final/calib_Final_Muon_FullSetE_1_calib.txt`.

The run table is the single source of truth. The pedestal rule binds only
`type=pedestal` and inherits the compatible run number, requiring yall-run PR
#33 (`1081e9dd39418262588248272618130ce0503b8a`).

## Compare with the published calibration

```tcsh
python3 ../compare_fullset.py --set-name FullSetE_1
```

The common tool compares refinement stages and builds combined PDF plot books,
using `pdfunite`, `qpdf`, or Ghostscript.

## Reuse converted data for a fresh analysis

`Yallfile.after-convert` reads existing `rawHGCROC_372.root` through
`rawHGCROC_378.root` from `LFHCAL_CONVERTED`. Those files must come from the
same V2 mapping and FullSetE_1 runs as the original recipe. Use a new
`LFHCAL_WORK`; keep the earlier outputs as the comparison baseline.

The 19-task plan contains seven nonempty-input checks named `reuse-*` instead
of conversion processes. It then reruns the muon merge, pedestal fitting,
calibration transfer, initial MIP fitting, selection, all five refinements and
final export. No symlinks or overwrite mode are needed. All analysis commands
and fit options are identical to the original recipe.

In the host tcsh shell, after setting `LFHCAL_CONVERTED` and a fresh
`LFHCAL_WORK`:

```tcsh
mkdir -p "$LFHCAL_WORK/campaigns"
cd "$LFHCAL_REPO/examples/yall/fullset-e1-repro"
yall-run validate Yallfile.after-convert
yall-run plan Yallfile.after-convert
set C = `yall-run create Yallfile.after-convert --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C"
```

Do not source `env.tcsh` after setting these variables. Run builds and tests
before submission and keep the build unchanged while the campaign is running.
The seven input checks confirm only that files are nonempty; the analysis
programs subsequently open them as ROOT inputs.

After completion, compare using the explicit new output path:

```tcsh
python3 "$LFHCAL_REPO/examples/yall/compare_fullset.py" \
    --set-name FullSetE_1 --work "$LFHCAL_WORK/fullset-e1-repro" --no-pdf
```

The workflow regression check uses the same Yall parser as the existing
shared-conversion tests:

```sh
python3 examples/yall/test_fullset_e1_reuse.py
```

## Test final export inside refine5

`Yallfile.test-inline-final` is a separate variant of `Yallfile.after-convert`.
It has 18 tasks: `refine5-e1` now declares and copies the final ROOT and
calibration files after DataPrep succeeds, eliminating the separate final
batch job. The `&&` chain stops before copying if DataPrep fails. Preparation,
input checks, analysis options and output filenames are otherwise unchanged.

Use a fresh `LFHCAL_WORK` and pass `Yallfile.test-inline-final` to the same
validate, plan and create commands above. Existing campaigns keep their
frozen recipes. This workflow-only change requires no C++ rebuild.

`python3 examples/yall/test_fullset_e1_inline_final.py` checks the task graph
and output ownership, and executes the final command with a fake DataPrep to
verify successful copies and rejection of partial outputs after failure.

## Test host-side setup without bookkeeping batch jobs

`Yallfile.test-host-setup` has ten batch jobs, starting directly with the muon
merge and pedestal fitting. It keeps the final copies inside refine5 and
removes `prepare` and the seven standalone converted-input checks.

Run the lightweight setup on the submission host before creating the campaign:

```tcsh
# Set LFHCAL_CONVERTED to the existing inputs and LFHCAL_WORK to a fresh directory.
cd "$LFHCAL_REPO/examples/yall/fullset-e1-repro"
python3 prepare_host.py
yall-run validate Yallfile.test-host-setup
yall-run plan Yallfile.test-host-setup
set C = `yall-run create Yallfile.test-host-setup --campaigns-dir "$LFHCAL_WORK/campaigns"`
yall-run start "$C"
yall-run status "$C"
```

Stop if setup fails. It checks that all seven converted files are readable
and nonempty before creating output directories, refuses an already-used
analysis directory, and records its inputs in `$LFHCAL_WORK/host-setup.json`.
It requires only host Python; it does not enter EIC, open ROOT files or submit
jobs. Host readability does not replace the batch nodes' own input access.
Do not reuse the work directory of a running campaign.

All analysis commands, input order and output filenames match the inline-final
variant. This is a workflow change only; no C++ rebuild is needed. The focused
regression check is `python3 examples/yall/test_fullset_e1_host_setup.py`.
