# Landau-Gaussian sampling sheets

The two PDFs in [`output/pdf`](../../output/pdf) use generated functions only; no detector histograms or event data enter the plots. They compare the original 100-midpoint convolution, the width-scaled implementation in `TileSpectra::langaufun`, and a dense midpoint reference using the same Landau function and integration interval.

The 8-by-8 sheet varies Landau width across columns (0.08 to 1.6 ADC) and Gaussian sigma across rows (0.4 to 12 ADC). Each curve has MPV 0 and area parameter 1. The horizontal coordinate is divided by the sum of the two widths, and each PDF is divided by its reference peak so the shapes remain visible at every scale. The corner number is the maximum absolute difference from the reference, divided by that peak, over the plotted range. The diagnosis sheet maps the same errors and the adjusted midpoint count, then enlarges the region near the old E1 cell 896 fit and shows where the midpoint samples land relative to the narrow Landau peak.

The reference uses `max(4000, ceil(200 * sigma / width))` midpoint steps over the interval `x +/- 5 sigma`. Its spacing is therefore at most one-twentieth of a Landau width: **at least 20 samples per width**. The adjustment uses at least five samples per width, retains the original 100-step minimum, and caps the count at 10,000. This grid stays below the cap. These sheets test numerical sampling, not fit convergence or scientific calibration quality.

With ROOT and `rsvg-convert` available, reproduce from the repository root in Bash:

```bash
cmake -S NewStructure -B NewStructure/build
cmake --build NewStructure/build --target LFHCAL -j 4
c++ -O2 -std=c++20 NewStructure/fit-study/plot_langau_grid.cc -INewStructure -LNewStructure/build -lLFHCAL -Wl,-rpath,"$PWD/NewStructure/build" $(root-config --cflags --libs) -o /tmp/plot_langau_grid
/tmp/plot_langau_grid /tmp/langau-grid-svg
mkdir -p output/pdf
rsvg-convert -f pdf -z 2.5 -o output/pdf/langau_width_grid_8x8.pdf /tmp/langau-grid-svg/langau_width_grid_8x8.svg
rsvg-convert -f pdf -z 2.5 -o output/pdf/langau_sampling_diagnosis.pdf /tmp/langau-grid-svg/langau_sampling_diagnosis.svg
```
