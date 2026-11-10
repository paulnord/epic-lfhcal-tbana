# Run 302 waveform annotations only

Run 302 was intentionally excluded from the November 9 raw-data rebuild because
its independently completed calibrated event input survived. It still needs
annotation PDFs before joining the combined normalized/unnormalized books.

`prepare_waveform_annotations.py --runs 302` selects only that run. The default
remains all 23 scans. This preserves the existing successful calibration/attempt,
configuration hash, immutable input, and native output checks. It does not rerun
conversion, calibration, or any other scan. Missing provenance fails preparation;
do not bypass it by editing the manifest.

From a **fresh clone with initialized submodules** in a new scratch base, run:

```sh
/bin/bash /absolute/fresh/base/source/examples/yall/ari-rf-batch/launch_run302_annotations.sh /absolute/fresh/base
```

This syntax works from tcsh as well as Bash. The launcher uses the known completed
run302 source campaign by default and the established `/star/u/pnord/bin/eic-shell`.
It prints the input and two-node plan, then asks for `SUBMIT 302`. It never changes
an old source checkout, old campaign, or calibrated data. The existing host
`yall-run` must be version 0.12.0a7 or newer.

All ROOT work runs on Condor: build/test/structural input verification, then one
waveform task. Queue time is unpredictable. This package has offline graph and
worker-path tests, not a new BNL/ROOT execution result.

Inspect `campaign-path.txt` for the submitted campaign. Products are under:

```
BASE/work/products/plots/waveform/Run302/
```

Collect these together (including any native subdirectory):

- `WaveformGrid_Run302_Annotated.pdf`
- `WaveformGrid_Run302_Original.pdf`
- `WaveformGrid_Run302_Measurements.csv`

The annotated PDF has an absolute-amplitude page followed by a normalized page.
Add the corresponding page to each combined book at run302's scan setting, not
at the end in run-number order. Keep the existing pages and large setting headers.
