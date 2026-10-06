# PS-2026 and SPS parameter-scan Yallfiles

`prepare_calibration_yallfiles.py` writes one native Yallfile per PS named set
and one per SPS parameter-scan group. Python only prepares the files; the
scientific commands and their switches are directly in each Yallfile.
Nothing is submitted by the setup command.

Every file contains:

* `@table runs type run` for pedestal, muon and any unpaired raw runs;
* `@table pairs ped sample` for the pedestal associated with each calibrated sample;
* explicit build, conversion, pedestal extraction, transfer, initial MIP,
  selection, refinement and final-constant tasks.

Readable copies for all twenty sets are checked in under `recipes/`. They use
`CALWORK`, `LFHCAL_RAW` and `EIC_SHELL` environment variables. Use the setup command
below to create the source snapshots, build directories and Yallfiles with
your actual paths; the checked-in copies are for inspection.

The PS muons within a named set are merged. SPS scan settings are **never
merged together**: Set1 has 6 pairs, Set2 has 2, and Set3 has 20. These names
follow Fredi's `calibMuonParScan` recipe, rather than the earlier, smaller
`scan-set-1` and `scan-set-2` examples.

## Readiness and open associations

| Sets | Recipe status |
|---|---|
| PS C1, C2, D1, D2, E1, E2 | Complete pedestal and ToA assignments in Fredi's recipe; generated as `Yallfile` |
| SPS Param1, Param2, Param3 | Complete per-run pairs and ToA assignments; generated as `Yallfile` |
| PS A1, A2, B1, B2, F1, F2, G1, G2, H1, I1, I2 | Inferred pedestal associations and missing named-set ToA choices; generated as `Yallfile.draft` |

“Complete” describes the recipe, not a completed or scientifically accepted
calibration. D1 retains the script's pedestal 238 despite the recorded CC
mismatch. G1 retains the proposed 379 in its draft. No automatic replacement
with 265 or 404 is made. The dead-time mismatches and other source notes remain
in each recipe and Yallfile header.

H1 and I1 currently reference the same muon runs; this is not two independent
data samples. I2's muons come from recipe comments, without an active merge.
For these three sets the source's active V2 inverse mapping is recorded along
with its conflicting V1 comments. None is promoted to a complete recipe.

The catalog is `calibration_2026_sets.json`. Its source recipes and run lists
are pinned to commit `5227c3e714e3be16b21a24bb76a99ecb8e85a2a5`.

## Prepare at BNL (tcsh)

The checkout need not change branches. These commands snapshot committed
sources and the decoder into a new output directory. The existing working
tree and previous campaigns are not changed.

```tcsh
set REPO = ~/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark
set RAW = /gpfs01/star/pwg/pnord/eic/2026TBanalysis/calibration-raw
set CALWORK = /gpfs01/star/scratch/pnord/lfhcal/ps-sps-calibration-20261006

git -C "$REPO" fetch origin codex/adaptive-langau-minimal && \
git -C "$REPO" show FETCH_HEAD:prepare_calibration_yallfiles.py > /tmp/prepare_calibration_yallfiles.py && \
python3 /tmp/prepare_calibration_yallfiles.py --repo "$REPO" --ref FETCH_HEAD \
  --raw "$RAW" --out "$CALWORK" \
  --eic-shell "$HOME/my_eic_work_with_LFHCAL/eic-shell"

cd "$CALWORK/ps-c1" && yall-run validate && yall-run plan
```

If the decoder has never been initialized in this checkout, setup reports that
before creating the output directory. Initialize it with:

```tcsh
git -C "$REPO" submodule update --init NewStructure/h2g_decode
```

Setup may run while downloads continue. `run-files.csv` records local presence
and nonempty size only; it does not query JLab or claim transfer integrity.
Wait for the downloader to finish successfully before starting calibration.
`ready-sets.txt` lists the nine complete recipes; `draft-sets.txt` lists eleven
unresolved ones. Each directory also contains `recipe.json`.

Use `--sets ps-c1 sps-param1`, for example, to prepare a subset. Each campaign
gets its own build directory, so concurrently running different sets cannot
overwrite a shared build. Converted files and pedestal products are shared
within a campaign, not across separate set campaigns.

## Scientific switches

| Step | Command and purpose |
|---|---|
| Raw conversion | `Convert -d 0 -f -w -c ... -m ... -r ...`; campaign-specific mapping and run database |
| Pedestal extraction | `DataPrep -a -d 1 -p ...`; pedestal-only converted run, text constants, histograms and PNG plots |
| Muon merge (PS only) | `hadd`; only runs whose table type is `muon` |
| Pedestal/quality transfer | `DataPrep -d 1 -e -f -P ... -B ... -G ...`; pedestal constants, bad-channel map and assigned ToA offsets |
| Initial MIP | `DataPrep -a -f -d 1 -e -s ...` |
| MIP event selection | `DataPrep -f -d 1 -X ...` |
| Refinement 1 | `DataPrep -x -a -f -d 1 -S ...` on the selected event file |
| Refinements 2–5 | Same selected event file, with `-k` pointing to the preceding pass's calibration text |
| Final constants | Copy the final refinement's ROOT calibration and calibration text into `final/` |

Every fit pass preserves ROOT histograms and text constants. Plots use PNG,
avoiding the earlier ROOT PDF rendering issue. `-x` avoids writing another
large event tree at every refinement. There is no `fixSetup` pass: the raw
conversion uses the selected mapping from the outset. Applying calibrations
to separate pion/hadron samples and waveform studies are outside this raw
calibration campaign.

Default: **Legacy fitter, original boundary, five refinements**, matching the
earlier F1 workflow. Five is our campaign choice, not a claim that every PS
set has a published R5 calibration. Use `--refinements 4` for an R4 comparison
or another explicit count if that is the desired stopping point.

Options `--fitter adaptive` and `--boundary valley` apply the existing tested
patches to the frozen source snapshot. Use a different `--out` for every
variant. The valley patch affects refinement range selection, leaving initial
MIP range selection unchanged. This setup does not automatically launch all
four fitter/boundary combinations.

Analysis sources are pinned to `d689941726f35e4eba8fc7586b9de4f3d31a3bb7`
(unpatched Legacy source); decoder to
`2a7f7d4e8b760ff9f9406e36d31e99c5b6fffa2c`. `manifest.json` records the
bundle revision, options and associations, and `source-hashes.json` records
the prepared source contents.

## Resolving the drafts

Supply `--overrides decisions.json` with an object keyed by PS set name.
Allowed fields are `pedestal` (integer), `toa` (config filename or absolute
path), `mapping` (config filename or absolute path), and `muon_runs` (integer
list). An inferred pedestal needs an explicit `pedestal` choice even if its
number stays the same. Missing ToA needs an explicit `toa` choice. The value
`"none"` deliberately omits `-G`; it is not selected automatically.

Generate into a new directory after those choices are settled. Preserve and
review the H/I mapping and merge notes when making the decisions.

## Validation

Offline tests use the actual yall-run parser to expand all twenty recipes.
They verify dependencies for generated inputs, pedestal exclusion from PS
merges, exact SPS pairing, unpaired-run exclusion, constant selected-event
inputs, previous-pass calibration inputs and draft handling.

```sh
python3 -m unittest -v test_calibration_yallfiles.py
```

The setup and graph checks do not execute ROOT or demonstrate the quality of
the new PS/SPS fits. The first BNL build and pilot calibration remain the
runtime check.
