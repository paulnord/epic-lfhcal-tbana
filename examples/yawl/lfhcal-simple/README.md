# Simple LFHCal Yawl example

Start here for the LFHCal examples.

This Yawlfile demonstrates three common workflow patterns without trying to describe a full production analysis:

1. Convert a list of raw runs.
2. Create calibrations from a list of pedestal/MIP pairs.
3. Create summaries from another list of runs.

The example deliberately uses a simple `converted` barrier. It waits for all raw conversions before starting the calibration and summary tasks. The production scan-set examples use finer-grained dependencies for more parallelism.

## Setup

Build the LFHCal executables in `NewStructure/build` and define the TB2026 data root:

```tcsh
setenv LFHCAL_DATA /gpfs01/star/pwg/pnord/eic/2026TBdata
```

Then from this directory:

```tcsh
yawl-run validate
yawl-run plan
```

The campaign uses the local backend so the example stays focused on Yawl syntax. Use `--backend condor` at campaign creation time when you want to exercise the Condor backend.

The example processes only the first 1000 events in the `DataPrep` and `HGCROCStudy` tasks. Raw conversion still converts the selected input runs normally.
