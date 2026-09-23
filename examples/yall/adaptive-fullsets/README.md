# Adaptive FullSet F test workflows

These two Yallfiles add the omitted FullSet F calibration sets to the adaptive
production test. They use one correlated `@table runs type run:` definition per
set and run the complete chain from raw `.h2g` files:

- conversion of pedestal and muon runs;
- muon merge and pedestal calibration;
- transfer calibration and MIP calibration;
- corrected `-M` event skim;
- five adaptive improvement passes and final output copying.

`Yallfile.f1` uses pedestal 431 and muon runs 426--430. `Yallfile.f2` uses
pedestal 471 and muon runs 472, 475, 476, 479, 480, and 483. Inputs are read
from `{LFHCAL_DATA}/RunNNN.h2g`; the output tree is written below
`{LFHCAL_WORK}/adaptive-fullset-f{1,2}-repro`.

Validate and launch from this directory with:

```tcsh
yall-run validate Yallfile.f1
yall-run validate Yallfile.f2
```
