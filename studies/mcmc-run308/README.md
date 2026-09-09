# Run 308 MCMC fit study

Standalone scripts for the Run 308, cell 1473 `refine1` check of the LFHCal MIP Langau fit.

This real-data study compares two ROOT solutions for the same histogram and production fit range:

- `QRLMNE0` broad solution: MP = 61.9291, Landau width = 4.8844, Gaussian sigma = 20.9411
- `QRLN0` collapsed-sigma solution: MP = 67.6173, Landau width = 8.4137, Gaussian sigma = 0.0511

For this histogram the collapsed point is worse by about `Delta NLL = 48.18`. MCMC chains initialized at either point move into the broad posterior basin.

## Mac setup

Use a Python environment in which PyROOT works, then install the ordinary Python dependencies into that same environment.

```bash
python3 -c 'import ROOT; print(ROOT.gROOT.GetVersion())'
python3 -m pip install numpy matplotlib
```

No LFHCal shared library is required for this study. `production_langau.py` compiles the production `TileSpectra::langaufun` numerical model at runtime through ROOT's interpreter.

## Input data

Copy the Run 308 refine1 ROOT histogram file to the Mac. The scripts read the normal LFHCal ROOT file directly and recursively locate `IndividualCellsTrigg/hspectramipTriggADCCellID1473`.

## Quick run

```bash
chmod +x run_local_8chains.sh
./run_local_8chains.sh /path/to/rawHGCROC_wPedwMuon_wBC_ImpR_308_Hists.root
```

The launcher runs eight local chains in parallel: chains 00-03 start at the broad ROOT solution and chains 04-07 start at the collapsed-sigma solution. Each chain runs 20,000 iterations; the combine step discards 3,000 iterations per chain, leaving 136,000 retained samples.

The main outputs are `summary.txt`, `plots/sigma-traces.png`, `plots/landau_width-vs-sigma.png`, and `plots/data-and-solutions.png`.

The exact Run 308 cell 1473 production range, pedestal sigma, average MIP scale, ROOT reference points, and parameter bounds are currently encoded as defaults in `run_refine1_chain.py`. This is a reproducibility study, not yet a generic all-cell MCMC fitter.
