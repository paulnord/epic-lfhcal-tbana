# `make-tb2026-paramscan-campaign`

This tool generates one inspectable `lfhcal-run` manifest for the established
TB2026 parameter-scan calibration sequence. It only writes a job file; it does
not execute commands or submit Condor jobs.

## Generated sequence

For pedestal run `P` and muon run `M`, the manifest contains 12 jobs:

1. Create the output and plot directories.
2. Convert `RunP.h2g` and `RunM.h2g` independently.
3. Extract the pedestal calibration from run `P`.
4. Transfer that pedestal calibration to run `M` with bad-channel and ToA
   corrections.
5. Extract the initial muon calibration.
6. Select the MIP-trigger sample.
7. Perform three reduced calibration refinements (`ImpR`, `Imp2R`, `Imp3R`).
8. Apply `Imp3R` to the selected muon sample.
9. Run waveform analysis on the calibrated output.

Dependencies ensure the calibration steps remain ordered while the two raw
conversions may overlap.

## Example

```console
python3 tools/make-tb2026-paramscan-campaign \
  --pedestal-run 296 \
  --muon-run 298 \
  --raw-dir /gpfs01/star/pwg/USER/eic/2026TBdata \
  --output-dir /gpfs01/star/pwg/USER/eic/2026TBdata/full-chain-296-298 \
  --manifest full-chain-296-298.txt \
  --check
```

Inspect `full-chain-296-298.txt`, then use it locally or with Condor:

```console
python3 tools/lfhcal-run -j 2 full-chain-296-298.txt
python3 tools/lfhcal-run --condor full-chain-296-298.txt
```

The full BNL Condor invocation normally also supplies the EIC container wrapper
and pinned environment options documented in [`lfhcal-run.md`](lfhcal-run.md).

## Inputs and defaults

Required raw inputs are `RunP.h2g` and `RunM.h2g` under `--raw-dir`. By
default the generator uses executables from `NewStructure/build` and these
repository files:

- `configs/TB2026/mapping_HGCROC_SPSH2TB_sumV2_default.csv`
- `configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv`
- `configs/TB2026/badChannel_HGCROC_SPSTB2026_OnlyCenter2x4.txt`
- `configs/TB2026/ToAOffsets_TBSPS2026_ParamScan_1.csv`
- `configs/TB2026/activeCellsHGCROCParameterScan.txt`

Each path has a command-line override. `--repository` selects the checkout and
`--build-dir` selects a different build directory.

`--check` requires all raw inputs, executables, and configuration files to
exist before the manifest is written. Omit it when intentionally preparing the
campaign before downloads or compilation finish. Use `--force` to replace an
existing manifest.

The former command name `make-tb2026-paramscan-dag` remains available as a
compatibility alias and produces the same campaign.
