# Monster adaptive-fit validation

`run_monster_validation.py` is the reproducible, audit-oriented entry point
for the full check. It does not overwrite calibration outputs. Every run gets
a new directory containing `manifest.json`, phase logs, and comparison results.

The protocol has four layers:

1. Build the isolated ROOT fitter and run all registered CTest checks.
2. Run the Python orchestration and reporting tests.
3. Compare legacy 100-point convolution, adaptive quadrature,
   `TF1Convolution`, and RooFit on the preserved E1 histograms. The fixed
   cells include the narrow-width examples 835, 896, and 898, the adaptive
   failure case 1223, the legacy outlier 640, and a normal control cell.
4. Run the seven-start fixed/adaptive stability matrix over the preserved HV
   cases. This is the expensive phase and is intended for BNL or a machine
   with the full ROOT inputs.

Optional production campaign directories can be passed with `--campaign`.
Their file inventory and provenance hashes are recorded; no campaign file is
changed. The result is `REVIEW` when warnings exist, even if all executed
commands pass. This is intentional: numerical checks do not by themselves
certify a calibration.

To compare completed calibration trees with the published TB2026 calibration,
pass each output tree with `--calibration-work`. The set name is inferred from
the conventional directory name, and `examples/yall/compare_fullset.py` writes
the numerical comparison into the audit bundle:

```bash
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-b1-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-b2-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-c2-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-c3-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-d1-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-e1-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-e2-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-e3-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-f1-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-f2-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-g1-repro \
--calibration-work /gpfs01/star/scratch/$USER/lfhcal/adaptive-fullset-g2-repro
```

The list covers the complete TB2026 production set used by this study:
B1, B2, C2, C3, D1, E1, E2, E3, F1, F2, G1, and G2.  A missing or
incomplete output remains an explicit validation failure; the harness does not
silently drop a set from the comparison.

Without this option, calibration files are only used as fit seeds by the
stability phase; the harness explicitly reports that no calibration comparison
was requested.

## Local smoke and comparison run

This executes the build, unit tests, Python tests, and E1 tool comparison while
leaving the long stability matrix out:

```bash
python3 examples/yall/hv44-delete-test/fit-study/run_monster_validation.py \
  --out local-results/monster-validation-$(date -u +%Y%m%dT%H%M%SZ) \
  --skip-stability --skip-campaign-audit
```

## Full local/BNL run

Use the EIC-shell wrapper on BNL so ROOT and the compiler are the same ones
used for the production executable. Supply the campaign directories after the
production runs have finished:

```tcsh
set STUDY = "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tbana-delete-test/examples/yall/hv44-delete-test/fit-study"
set OUT = "/gpfs01/star/scratch/$USER/lfhcal/monster-validation-`date -u +%Y%m%dT%H%M%SZ`"
"$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tbana-delete-test/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
  python3 "$STUDY/run_monster_validation.py" \
  --out "$OUT" --jobs 2 \
  --campaign "$LFHCAL_WORK/adaptive-fullsets/campaigns/lfhcal-tb2026-adaptive-fullset-b1-..." \
  --campaign "$LFHCAL_WORK/adaptive-fullsets/campaigns/lfhcal-tb2026-adaptive-fullset-f1-..."
```

Before starting the full matrix, verify that the selected cases and fitter are
on the same branch and that the output filesystem has room for logs and ROOT
result files. A failed phase preserves its log and partial results; fix the
cause and start a new output directory rather than mixing attempts.

The final `manifest.json` is the artifact to review with the group. It records
the study source hashes, input hashes, exact commands, elapsed times, return
codes, campaign inventories, and explicit warnings.
