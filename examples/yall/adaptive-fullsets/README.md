# Adaptive FullSet calibration replays

This directory contains calibration-only Yallfiles for the twelve FullSet
inputs already converted and merged under the persistent TB2026 layout. They
start with pedestal creation and do not reconvert raw data or merge muon runs.

The selector uses `-M`, which is the MIP-only path Fredi identified for the
calibration workflow. The adaptive branch changes only the Landau–Gaussian
numerical evaluator; the fit ranges, bounds, likelihood, and refinement chain
remain the existing choices.

Each Yallfile uses `%preflight` to create its output and plot directories on
the submit host. There is no queued `prepare` task; the first batch job is the
pedestal calculation.

Before running, make sure these files exist:

```text
/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata/converted/rawHGCROC_<pedestal-run>.root
/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata/merged/rawHGCROC_Muon_<FullSet>.root
```

On BNL:

```tcsh
cd "$LFHCAL_REPO/examples/yall/adaptive-fullsets"
source env.tcsh

foreach code (b1 b2 c1 c2 c3 d1 d2 e1 e2 e3 g1 g2)
    yall-run validate "Yallfile.$code"
end

foreach code (b1 b2 c1 c2 c3 d1 d2 e1 e2 e3 g1 g2)
    set C = `yall-run create "Yallfile.$code" --campaigns-dir "$LFHCAL_WORK/adaptive-fullsets/campaigns"`
    echo "$code $C"
    yall-run start "$C"
end
```

Each campaign creates its own output under:

```text
$LFHCAL_WORK/adaptive-fullset-<code>-repro/
```

The final calibration is in the `final/` directory. The generated campaigns
are independent after input files are in place, so they can run concurrently
subject to the BNL queue and storage limits.
