# Simple LFHCal Yall example

Start here for the LFHCal examples.

This Yallfile demonstrates three common workflow patterns without trying to describe a full production analysis:

1. Convert every unique run from a top-level pedestal/MIP table.
2. Fit each pedestal once and calibrate the correlated pairs.
3. Create summaries from the MIP column, without repeating the run list.

The `pairs` table is the single source of run numbers. `@each run in pairs.ped pairs.mip` creates one conversion per unique run, even when a pedestal is shared. Pedestal fitting waits only for its own conversion; each calibration waits for its pedestal fit and MIP conversion. Summaries wait only for their own conversion. There is no all-conversions barrier. The default example has 16 tasks.

Use a yall-run checkout with combined named-source support from PR #26 (`feat/each-source-union` until merged); PR #25 alone supports only one source after `in`. See the parent README for runner setup. Existing frozen campaigns are unaffected.

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
