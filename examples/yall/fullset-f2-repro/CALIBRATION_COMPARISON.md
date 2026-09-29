# FullSet F2 calibration comparison

This note records a numerical validation of the `fullset-f2-repro` workflow
against Fredi's published FullSetF_2 calibration. It is an analysis check of the
reproduction workflow, not a description of the dataset.

Comparison performed: **September 17, 2026**.

## Files compared

Published reference:

```text
calibrations/TB2026/calib_SPS-H2_FullSetF_2.txt
```

Reproduced final calibration:

```text
$LFHCAL_WORK/fullset-f2-repro/final/calib_Final_Muon_FullSetF_2_calib.txt
```

The reproduced pedestal, initial MIP calibration, and all five refinement tables
were also retained and compared with the published final calibration to inspect
convergence.

## Result

The reproduction agrees very closely with the published calibration.

- Both final tables contain the same 384 cell IDs and identical geometry.
- Both contain 380 positive HG MIP scales and the same four unavailable scales.
- The median absolute relative HG MIP-scale difference is `0.000003374%`.
- The largest absolute relative HG MIP-scale difference is `0.005241889%`.
- All 380 positive scales agree within `0.01%`; 372 agree within `0.001%`.
- The reproduced final text file is byte-for-byte identical to the reproduced
  `Imp5R` text file, as expected from the Yallfile finalization step.

Relative differences here are

```text
100 * (reproduced - reference) / reference
```

and are evaluated only where both stored quantities are positive.

The largest relative scale difference occurs at cell 1088:

| value | Fredi | reproduced |
|---|---:|---:|
| HG MIP scale | 17.798927 | 17.799860 |

The difference is `+0.000933`, or about `+52.4 ppm`.

The 12 largest relative scale differences are localized in modules 2 or 3,
row 0, column 1. They are very small, but the localization is worth preserving
as a clue if the residual numerical differences are investigated later.

## Refinement convergence

Each reproduced stage below is compared with Fredi's **final** table; Fredi's
intermediate refinement tables were not available for a stage-by-stage direct
comparison.

| reproduced stage | positive HG scales in both | median absolute difference | largest absolute difference |
|---|---:|---:|---:|
| Initial MIP | 372 | 0.820576% | 76.910828% |
| Imp1 | 380 | 0.030197% | 8.447758% |
| Imp2 | 380 | 0.000045% | 0.037918% |
| Imp3 | 380 | 0.000004% | 0.005242% |
| Imp4 | 380 | 0.000003% | 0.005242% |
| Imp5 | 380 | 0.000003% | 0.005242% |

Eight channels first acquire positive scales in Imp1. By Imp3 the calibration is
essentially settled; from Imp3 to Imp5 the largest positive-scale change is only
about `3.44 ppm`.

Cell 1351 has a conspicuous intermediate excursion in the stored HG MIP width:

| stage | HG MIP scale | stored HG MIP width |
|---|---:|---:|
| Initial MIP | 53.371104 | 35.157470 |
| Imp1 | 58.716285 | 1.380049 |
| Imp2 | 54.146596 | 38.125254 |
| Imp5 | 54.142418 | 38.118359 |
| Fredi final | 54.142461 | 38.118655 |

The final result nevertheless converges closely to the reference. The stored
width is a calibration width, not an uncertainty on the fitted MIP scale.

## Pedestals and shared missing calibrations

Pedestal values also agree closely. The largest absolute differences in the
stored pedestal quantities are:

| pedestal field | largest absolute difference |
|---|---:|
| HG mean | 0.000511 |
| HG sigma | 0.000606 |
| LG mean | 0.000227 |
| LG sigma | 0.000051 |

The same four cells have HG MIP scale and width equal to `-1000` in both final
tables:

| cell | module | layer | row | column | BC |
|---:|---:|---:|---:|---:|---:|
| 967 | 1 | 7 | 1 | 3 | 0 |
| 1026 | 2 | 2 | 0 | 0 | 3 |
| 1031 | 2 | 7 | 0 | 0 | 0 |
| 1924 | 3 | 4 | 1 | 2 | 3 |

Cells 1026 and 1924 also lack HG pedestal mean and sigma values in both the
reproduced pedestal output and the published final table. These are therefore
shared calibration gaps, not failures introduced by the reproduction.

## Conclusion

The FullSetF_2 Yall workflow passes this numerical reproduction check. It
recreates the published final calibration with the same channel coverage and
very small residual numerical differences, and the refinement sequence converges
stably to that result.

This comparison validates the exported calibration constants. It does not by
itself validate ROOT histogram identity, fit covariances, individual
Landau/Gaussian component parameters, event-by-event identity, or the exact
runtime/container environment used for the original published calibration.
