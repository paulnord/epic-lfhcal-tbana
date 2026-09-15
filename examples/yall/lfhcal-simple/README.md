# Simple LFHCal Yall example

Start here for the LFHCal examples.

This Yallfile demonstrates three common workflow patterns without trying to describe a full production analysis:

1. Convert a list of raw runs.
2. Create calibrations from a list of pedestal/MIP pairs.
3. Create summaries from another list of runs.

The example deliberately uses a simple `converted` barrier. It waits for all raw conversions before starting the calibration and summary tasks. The production scan-set examples use finer-grained dependencies for more parallelism.

## Setup

Build the LFHCal executables in `NewStructure/build` and define the TB2026 data root:

```tcsh
setenv LFHCAL_DATA /path/to/TB2026/raw-data
```

Then from this directory:

```tcsh
yall-run validate
yall-run plan
```

The campaign uses the local backend so the example stays focused on Yall syntax. Run it inside your EIC software environment. This Yallfile has no container wrapper; overriding the backend alone does not supply one. For host-side Condor submission with an installed `eic-shell` wrapper, use `hgcroc-study-condor` or the production scan-set examples and follow the parent README.

The example processes only the first 1000 events in the `DataPrep` and `HGCROCStudy` tasks. Raw conversion still converts the selected input runs normally.
