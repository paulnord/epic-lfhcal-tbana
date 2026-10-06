# PS-2026 and SPS parameter-scan Yallfiles

The files in `../ps-*/` and `../sps-param*/` are the actual Yallfiles, directly
under `examples/yall/` alongside the other examples. Edit them directly, then use
`yall-run validate`, `yall-run plan`, and the normal campaign commands.
There is no Python preparation or generation step.

Each file contains `@table runs type run` for raw conversion, `@table pairs
ped sample` for pedestal associations, and the explicit commands for the
whole calibration chain. The accompanying JSON catalog records the source
notes; it is not read when running a Yallfile.

## Use at BNL (tcsh)

Use the existing LFHCal source/configuration checkout and compiled executables.
With the examples in that checkout:

```tcsh
setenv LFHCAL_SOURCE "$HOME/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark"
setenv CALWORK /gpfs01/star/scratch/pnord/lfhcal/ps-sps-calibration-20261006
setenv LFHCAL_RAW /gpfs01/star/pwg/pnord/eic/2026TBanalysis/calibration-raw
setenv EIC_SHELL "$HOME/my_eic_work_with_LFHCAL/eic-shell"

cd "$LFHCAL_SOURCE/examples/yall/ps-c1"
yall-run validate && yall-run plan
```

Each Yallfile has `@set BUILD {SOURCE}/NewStructure/build`. Edit that line if
using a different existing build. There are no CMake, make, compilation, or
source-checkout tasks in these calibration campaigns. Select the existing
build for the intended fitter; the current recipe labels describe Legacy
with the original boundary.

The `%preflight` commands perform lightweight host setup during
`yall-run create`:

* Check that `Convert`, `DataPrep`, the analysis library and EIC shell exist
  with the needed permissions.
* Create stage and plot parent directories under `CALWORK`.
* Copy the small build-directory/library wrapper into the set's work directory.

`validate` checks declarations and `plan` displays the preflight commands;
only `create` executes them. A failed preflight prevents creation of a
launchable campaign. It adds no scheduler jobs. The preflight uses file
checks only; it does not compile or run the ROOT programs on the login host.

The shared wrappers and this README live in `examples/yall/calibration-2026/`.
Each Yallfile loads them relative to its own example directory, so keep that
shared directory when copying examples elsewhere.
The runtime wrapper selects the existing build directory and library; it
contains no calibration commands or run lists. All scientific processing
stays in normal batch tasks, beginning with raw conversion.

Wait for the required raw downloads to finish successfully before starting
a calibration campaign. Keep the selected source/build fixed while it runs,
and use a new `CALWORK` for another calibration variant.

## Recipes and unresolved choices

| Sets | File and status |
|---|---|
| PS C1, C2, D1, D2, E1, E2 | `Yallfile`: pedestal and ToA assignments present in Fredi's recipe |
| SPS Param1, Param2, Param3 | `Yallfile`: complete pedestal–muon pairs and ToA choices |
| PS A1, A2, B1, B2, F1, F2, G1, G2, H1, I1, I2 | `Yallfile`: inferred pedestal associations; H/I also have mapping/merge questions |

All twenty examples use the filename `Yallfile`. Association uncertainties
remain in their header comments and in the inventory notes. Edit any changed
pedestal/mapping choices directly in the Yallfile.

External ToA offsets are optional for this ADC/MIP calibration. The code
loads them only when `-G` is supplied; Fredi's helper supports both `BC`
(without offsets) and `BCTOA` (with offsets). ADC integration, the local muon
selection and the MIP fit do not use the corrected ToA in this workflow.
Known recipe offsets remain included. Where none is assigned, the Yallfile
omits `-G` and the ToA-file input. Timing/waveform-alignment diagnostics in
those outputs must not be treated as phase-calibrated. Missing ToA is not a
reason to hold up the MIP calibration.

D1 preserves pedestal 238 from the script despite its recorded CC mismatch;
G1 preserves 379. Neither is silently replaced by 265 or 404.
Dead-time mismatches and other source notes remain in each file's header.
H1 and I1 currently contain the same muon runs. I2 is based on recipe
comments without an active merge. Their active V2 inverse mapping conflicts
with V1 comments in the original script; these caveats remain documented.

PS muons are merged within their named set. SPS scan runs are **never merged
across settings**: Param1 has 6 pairs, Param2 has 2, and Param3 has 20. Those
group names follow Fredi's `calibMuonParScan` recipe. Extra unpaired SPS runs
are converted, but do not enter calibration chains.

The inventory was transcribed from conversion/calibration recipes and run
databases at `5227c3e714e3be16b21a24bb76a99ecb8e85a2a5`. The Yallfiles are
now the editable execution recipes; the JSON records the inventory and association notes.

## Calibration sequence

| Step | Main switches / inputs |
|---|---|
| Convert raw | `Convert -d 0 -f -w -c ... -m ... -r ...` |
| Fit pedestals | `DataPrep -a -d 1 -p ...` on pedestal-only converted data |
| Merge PS muons | `hadd`, excluding pedestal files |
| Transfer constants | `DataPrep -d 1 -e -f -P ... -B ... -G ...` |
| Initial MIP calibration | `DataPrep -a -f -d 1 -e -s ...` |
| Select MIP events | `DataPrep -f -d 1 -X ...` |
| Refine 1 | `DataPrep -x -a -f -d 1 -S ...` |
| Refine 2–5 | Same selected events, plus `-k` with the preceding calibration text |
| Final | Copy R5 calibration ROOT and text files to `final/` |

These Yallfiles are labelled for **Legacy with the original boundary** and
run five refinements, as in F1, and preserve per-stage histograms,
calibration text and PNG plots. Five passes are our workflow choice, not a
claim that every PS set has a published R5 calibration. `-x` avoids repeated
large event-tree outputs. Fresh conversion uses the selected mapping, so
there is no later `fixSetup` pass. Separate pion/hadron processing and
waveform studies are outside this calibration chain.

## Validation

`python3 -m unittest -v test_calibration_yallfiles.py` reads the checked-in
Yallfiles using the actual yall-run parser. It checks all twenty task graphs,
PS merge membership, exact SPS pairing, input dependencies, previous-pass
constants and the preflight checks/directory setup using fixture executables.
The tests require yall-run, but not ROOT or raw data. Actual ROOT execution
and fit quality still need the first BNL run.
