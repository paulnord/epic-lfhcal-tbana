# Historical plotting routines (not a current passing gate)

Preserved unchanged from combined fork PR #14 head `0810773`. These routines
were written for an earlier PR #16 renderer. They are retained for review and
exploratory evidence, **not repaired or asserted compatible** with the current
plotting proposal. No production rendering, fitting API, or physics is changed.

## Requirements and known incompatibilities

This draft is independently based on main `9302328`. That base includes
`AdaptiveLangau.h`, but **does not include `FitCurveDrawing.h`**. All three
commands need ROOT/PyROOT and an explicitly supplied renderer checkout via
`--source-dir /path/to/NewStructure`; figure generation also needs matplotlib.
An absent renderer is a prerequisite error, not a successful skipped test.
Supplying the current renderer does not make the historical regression valid.

Against the rebased plotting proposal at `d67f6ff`:

- `test_fit_curve_drawing.py` expects fit-range clipping, whereas the current
  sampler uses the requested visible range. Its first range assertion fails.
- It uses the removed five-argument `DrawMipFit(fit, histogram, lo, hi, color)`;
  the current interface is `DrawMipFit(fit, lo, hi)`.
- It expects removed bin-prediction overlays, rejected-fit diagnostics
  (`DrawRejectedMipFits` / `GetSignalFitAttempt`), and an empty graph outside
  the fit range. Those expectations are not the current plotting contract.

The unchanged regression was run against `d67f6ff` with ROOT 6.40.00 on
2026-10-26: **exit 1 at the first fit-range assertion**. The comparison/audit
scripts use `SampleMipFit`; they are not covered by that regression result and
have not been revalidated against that renderer in this split. Updating any
API expectations or scientific comparisons requires separate review.

## Historical commands (explicit opt-in; not CI)

From the repository root, with a deliberately chosen compatible historical
renderer checkout. These are reproduction commands, not a current pass recipe:

```sh
python3 NewStructure/tests/test_fit_curve_drawing.py --source-dir /path/to/historical/NewStructure
python3 NewStructure/tests/test_fit_curve_drawing.py --source-dir /path/to/historical/NewStructure --adaptive-header NewStructure/AdaptiveLangau.h
python3 NewStructure/tests/compare_fit_curve_samples.py --source-dir /path/to/historical/NewStructure --adaptive-header NewStructure/AdaptiveLangau.h --output /tmp/fit-evidence
python3 NewStructure/tests/audit_fixed_fit_curves.py --source-dir /path/to/historical/NewStructure --adaptive-header NewStructure/AdaptiveLangau.h --frozen-fits /tmp/fit-evidence/same-histogram-fit-curves.json --output /tmp/fixed-audit
```

The preserved regression historically checked live legacy/combined (optionally
adaptive) callbacks, fit-window clipping, bin-center predictions, unchanged
metadata, rejected-attempt labeling and the excessive-sampling guard. Several
of these are now stale, as detailed above. The historical cell-896 vector is
rounded to published precision, not a recovered beam histogram.

The comparison fits identical deterministic adaptive-generated histograms
with identical starts, bounds and options. It retains a narrow case and a
well-resolved control; this is **not an unbiased physical-model benchmark**.
The four-case audit does **no refitting**: it compares old and faithful drawing
of each frozen function. Controls C/D share one synthetic histogram but use
different fitted evaluators. Its B/C captions hardcode "saved fit status 0"
rather than validating imported fit status; do not infer status verification.
Generated images/data are review evidence, not checked-in test fixtures.
No current full-chain beam replay is claimed.

The separate `Diagnostic fixture integrity` workflow only checks fixture
bytes/records and Python syntax; it does not execute these plotting routines.
The baseline ROOT smoke workflow remains in PR #14, outside this draft.
