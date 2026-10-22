# Plotting checks (depends on plotting PR #16)

These exercise the MIP renderer, not the independent baseline smoke suite
in PR #14. They do not change production code. Requires ROOT/PyROOT;
figures additionally require matplotlib.

From the repository root:

```sh
python3 NewStructure/tests/test_fit_curve_drawing.py
# Optional adaptive compatibility; use the unchanged AdaptiveLangau.h from PR #89:
python3 NewStructure/tests/test_fit_curve_drawing.py --adaptive-header /path/to/AdaptiveLangau.h
python3 NewStructure/tests/compare_fit_curve_samples.py --adaptive-header /path/to/AdaptiveLangau.h --output /tmp/fit-evidence
python3 NewStructure/tests/audit_fixed_fit_curves.py --adaptive-header /path/to/AdaptiveLangau.h --frozen-fits /tmp/fit-evidence/same-histogram-fit-curves.json --output /tmp/fixed-audit
```

The regression checks live legacy/combined (optionally adaptive) callbacks,
fit-window clipping, bin-center predictions, unchanged metadata, rejected
attempt labeling and the excessive-sampling guard. The historical cell-896
vector is rounded to its published precision, not a recovered beam histogram.

The comparison fits identical deterministic adaptive-generated histograms
with identical starts, bounds and options. It retains a narrow case and a
well-resolved control; this is not an unbiased physical-model benchmark.
The four-case audit does **no refitting**: it compares old and faithful drawing
of each frozen function. Controls C/D share one synthetic histogram but use
different fitted evaluators. Generated images/data are review evidence, not
checked-in test fixtures. No current full-chain beam replay is claimed.
