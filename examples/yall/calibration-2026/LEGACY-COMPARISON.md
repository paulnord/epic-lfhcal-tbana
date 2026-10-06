# PS Legacy comparison

Each `ps-*/Yallfile.legacy` reuses that set's completed pre-MIP
`transfer/rawHGCROC_wPed_wBC_Muon_FullSet*.root` file. It runs eight tasks:
initial MIP fit, its own muon selection, refinements R1–R5, and final copy.
Pedestal associations, ToA corrections already applied during transfer, run
configuration, and refinement switches match the original PS recipe.

`build-legacy-comparison.sh` makes a separate copy of the active `NewStructure`
and `configs` directories, without old build products. It changes only the
`FitMipHG` dispatch to call `fitMipHGLegacy`, then builds DataPrep in the EIC
shell. This preserves the original fit boundary and the exact Legacy routine
present in the active checkout. It is intended for the AdaptiveMipFit helper
version with the dispatch shown in `legacy-dispatch.patch`; a different source
layout fails the patch check. It does not change the active checkout or build.
A successful retry reuses the private build without recompiling it.

## Fetch and build once (tcsh)

```tcsh
set REPO = ~/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark
set LEGACY = /gpfs01/star/scratch/pnord/lfhcal/ps-legacy-original-20261006
setenv PS_REFERENCE /gpfs01/star/scratch/pnord/lfhcal/ps-sps-calibration-20261006
setenv PS_LEGACY_SOURCE "$LEGACY/source"
setenv PS_LEGACY_WORK "$LEGACY/results"
setenv EIC_SHELL ~/my_eic_work_with_LFHCAL/eic-shell

mkdir -p "$LEGACY/recipes" && \
git -C "$REPO" fetch origin codex/adaptive-langau-minimal && \
git -C "$REPO" archive -o "$LEGACY/recipes.tar" FETCH_HEAD examples/yall && \
tar -xf "$LEGACY/recipes.tar" -C "$LEGACY/recipes" && \
bash "$LEGACY/recipes/examples/yall/calibration-2026/build-legacy-comparison.sh" "$REPO" "$PS_LEGACY_SOURCE" "$EIC_SHELL"
```

Wait for `Legacy comparison build ready` (or `already ready`) before submitting.
The build is a one-time setup action; the Yallfiles only preflight the build and
input file, create output directories, and install the existing runtime wrapper.

## Submit (tcsh)

These fifteen sets had completed their transfer stage in the supplied queue
snapshot. A1 and A2 also have recipes; add them once their transfer files exist.
Run this launch loop once; it writes campaign paths to `legacy-campaigns.txt`.

```tcsh
mkdir -p "$LEGACY/campaigns"
foreach psset (ps-b1 ps-b2 ps-c1 ps-c2 ps-d1 ps-d2 ps-e1 ps-e2 ps-f1 ps-f2 ps-g1 ps-g2 ps-h1 ps-i1 ps-i2)
    set yf = "$LEGACY/recipes/examples/yall/$psset/Yallfile.legacy"
    set cam = ( `yall-run create "$yf" --campaigns-dir "$LEGACY/campaigns"` )
    if ( $#cam != 1 ) then
        echo "Creation failed for $psset; stopping."
        break
    endif
    echo "$psset $cam" >> "$LEGACY/legacy-campaigns.txt"
    yall-run start "$cam"
    if ( $status != 0 ) then
        echo "Submission failed for $psset; stopping."
        break
    endif
end
```

The existing campaigns may say `legacy-original` in their names even when the
shared source dispatch uses Adaptive. The new names end in `legacy-compare`;
the private build and dispatch patch establish the method.

## Validation

`python3 -m unittest -v test_ps_legacy_yallfiles.py` checks all seventeen recipes
using the yall-run parser: eight-task dependency chains, private outputs/build,
shared pre-MIP input, independent Legacy selection, preceding-stage constants,
and preflight rejection of missing inputs, missing/changed builds, and identical
reference/output paths. ROOT and BNL data are not required for these wiring tests.
The actual ROOT build runs at BNL with the command above.
