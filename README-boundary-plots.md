# Four-way boundary flow plots at BNL

Run after `compare-b2` and `summary` complete. This is a standalone companion
 to `plot_fit_parameter_convergence.py`, using the same signed-log change scale
and deterministic cell colors. Python 3.9+, NumPy and Matplotlib are required;
ROOT and the large event files are not needed. It does not modify campaign inputs.

```tcsh
set REPO = ~/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark
set RANGEWORK = /gpfs01/star/scratch/pnord/lfhcal/boundary-fullchains-20261002
git -C "$REPO" fetch origin codex/adaptive-langau-minimal && \
git -C "$REPO" show FETCH_HEAD:plot_boundary_convergence.py > /tmp/plot_boundary_convergence.py && \
python3 /tmp/plot_boundary_convergence.py --root "$RANGEWORK" --out "$RANGEWORK/flow-plots" --pdf
```

Download `boundary-fullchains-20261002/flow-plots.zip`. Open `index.html` after
extracting it. The archive contains PNG/PDF figures, the existing campaign's
`all-stage-statistics.csv` (saved, available, carried-forward, timing), unclipped
fractional values in `flow-values.csv`, and SHA-256 input provenance.

There are 64 figures by default:

- Eight all-set flow figures: four parameters (H, MPV, Landau width, Gaussian
  sigma), each showing either consecutive-fit change or difference from that
  cell's **original Legacy R5**. Each figure has four panels: Legacy/Adaptive
  crossed with original/valley boundary. Dataset lanes keep the sets separate.
- Fifty-six absolute figures: one dataset and one parameter per figure, with
  those same four panels and shared linear scales. B2 extends through R8;
  all other sets stop at R5.

Only newly saved, finite fit parameters are plotted, including H. Carried-forward
calibrations remain in the statistics table but are not drawn as fresh fits.
A missing fit breaks its line; a step change requires both adjacent fits. Zero
reference denominators produce gaps. The original Legacy R5 reference is fixed
across all four panels; it does not change to valley Legacy R5.

MIP is reused, not independently rerun. R1 step change compares R1 with MIP.
Triangles indicate clipping at the signed-log display limit, **not failed fits**.
Black dots and bars show medians and central 68% of the valid values at each
stage, so the contributing cell population can vary. These descriptive summaries
do not establish that a method is better. Inspect absolute shifts and fit spectra.

All required stages and datasets are checked before plotting. Missing B2 R8 or
missing campaign summary stops the script. To intentionally plot fewer complete
sets, add `--datasets b1 e1 e2 e3`. Use a distinct output directory for subsets.
The input report fingerprints and all unclipped values are recorded. The code's
regression checks are synthetic and do not constitute scientific fit validation.

## Rendering performance

The renderer batches channel traces and markers, omits empty clipping markers,
and writes the numerical export one figure at a time. Dense channel layers are
rasterized inside PDFs; text and axes remain vector graphics. Fit values, gaps,
colors, display clipping and statistical summaries are unchanged. Progress is
printed during report loading, before drawing, before each PNG/PDF save, and
before ZIP packaging.
