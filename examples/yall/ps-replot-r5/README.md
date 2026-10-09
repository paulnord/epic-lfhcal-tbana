# Replay R5 and rebuild the report from tcsh

These are tcsh commands. Remain in your normal login shell. The existing `.sh`
wrappers select their own interpreter via their shebang; no interactive shell
switch or pasted shell program is required.

This runs 17 independent final-pass fits, using the completed Legacy selected
events and R4 constants. It recovers live callbacks and rejected attempts for
the faithful plots. It is an R5 replay, not pure redrawing of saved functions.
Conversion, pedestals, selection, and R1–R4 are reused. Earlier-stage HTML plots
are linked unchanged; the 459-page combined summary uses the regenerated R5
plots. Keep the old results and report as the comparison.

If the old results were archived elsewhere, replace `PS_REFERENCE` with the
directory containing `ps-a1`, `ps-a2`, ..., `ps-i2` and their selected events
and R4 calibration text. A report-only archive does not contain these inputs.

## Fresh checkout

```tcsh
setenv PS_REFERENCE /gpfs01/star/scratch/pnord/lfhcal/ps-legacy-pr86-pr87-20261007
set stamp = `date -u +%Y%m%dT%H%M%SZ`
setenv PLOT_WORK /gpfs01/star/scratch/pnord/lfhcal/ps-faithful-r5-$stamp
setenv PLOT_SOURCE "$PLOT_WORK/source"
setenv EIC_SHELL "$HOME/my_eic_work_with_LFHCAL/eic-shell"

mkdir -p "$PLOT_WORK" && \
git clone --branch codex/faithful-fit-plotting --recurse-submodules \
  https://github.com/paulnord/epic-lfhcal-tbana.git "$PLOT_SOURCE"
```

Stop if checkout or submodule initialization fails. If a previous Bash attempt
already produced a directory, leave it alone and use this fresh timestamp.

## Build and prepare

```tcsh
set support = "$PLOT_SOURCE/examples/yall/calibration-2026"
"$support/run-in-eic-shell.sh" "$EIC_SHELL" cmake \
  -S "$PLOT_SOURCE/NewStructure" -B "$PLOT_SOURCE/NewStructure/build"
"$support/run-in-eic-shell.sh" "$EIC_SHELL" cmake --build \
  "$PLOT_SOURCE/NewStructure/build" --target DataPrep -j 4

python3 "$PLOT_SOURCE/examples/yall/ps-replot-r5/prepare.py"
```

Proceed only after CMake finishes building DataPrep and preparation prints
`Prepared 17 R5 replay jobs`. The helper checks all selected-event/R4 inputs,
the unchanged Legacy fitter, and the executable/library; records their build
checksums; creates the output directories; links earlier plots; and copies the
checked-in Yallfile into `PLOT_WORK`. Repeating preparation with the same
configuration is safe. It rejects a changed build or conflicting setup.
Keep this source/build fixed while jobs run.

If an earlier preparation reported `declared outputs already exist` for the
`plots/refine5/Muon_FullSet*` directories, remove only those empty directories
and start the existing campaign:

```tcsh
rmdir "$PLOT_WORK"/ps-*/plots/refine5/Muon_FullSet* && \
yall-run start "$replot"
yall-run status "$replot" -v
```

`rmdir` refuses to remove a directory containing any results. No rebuild or
new campaign is needed. The corrected helper creates only the `refine5`
parent; DataPrep creates each declared sample directory itself.

## Submit once

```tcsh
cd "$PLOT_WORK"
yall-run validate && yall-run plan
set replot = ( `yall-run create "$PLOT_WORK/Yallfile" --campaigns-dir "$PLOT_WORK/campaigns"` )
```

Proceed only if create succeeded and returned one campaign directory. Then:

```tcsh
echo "$replot" > "$PLOT_WORK/campaign.txt"
yall-run start "$replot"
yall-run status "$replot" -v
```

If submission fails, inspect that campaign and retry `start` as appropriate;
do not run `create` again. To restore the variable in another tcsh session,
set `PLOT_WORK` to the printed run directory and run:

```tcsh
set replot = `cat "$PLOT_WORK/campaign.txt"`
yall-run status "$replot" -v
```

## Assemble after all 17 jobs succeed

```tcsh
python3 "$PLOT_SOURCE/assemble_ps_report.py" \
  --root "$PLOT_WORK" --out "$PLOT_WORK/report" --method legacy --pdf
echo "$PLOT_WORK/report/ps-2026-r5-report.pdf"
echo "$PLOT_WORK/report/index.html"
```

The assembler requires `reportlab`, as for the previous report. Its output
directory must be new; use a different `--out` name for a second assembly.
These commands generate local BNL outputs and do not publish the report site.
