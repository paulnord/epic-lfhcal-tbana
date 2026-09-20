# Collect complete HV-scan histograms

`collect_hv_histograms.py` packages the existing refine2 histogram files for all
nine HV-scan points, together with the preceding refine1 and current refine2
calibration tables. It uses Python 3.6+ and the standard library; ROOT and the
EIC shell are not required. It does not process events, refit, or change inputs.

## Download and run on BNL

The standalone script can be downloaded without changing the checked-out
calibration repository:

```sh
curl -fL -o collect_hv_histograms.py \
  https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/codex/hv-histogram-collector/examples/yall/hv44-delete-test/fit-study/collect_hv_histograms.py
python3 collect_hv_histograms.py \
  --work /gpfs01/star/scratch/$USER/lfhcal/hvscan-repro \
  --out-parent /gpfs01/star/scratch/$USER/lfhcal
```

The default includes all nine runs:

| Run | Bias voltage |
|---:|---:|
| 201 | 42 V |
| 202 | 42.5 V |
| 195 | 43 V |
| 196 | 43.5 V |
| 194 | 44 V |
| 197 | 44.5 V |
| 198 | 45 V |
| 199 | 45.5 V |
| 200 | 46 V |

For each run, the required paths under `--work` are:

```text
refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_RUN_Hists.root
refine1/rawHGCROC_wPedwMuon_wBC_ImpR_RUN_calib.txt
refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_RUN_calib.txt
```

The complete ROOT histogram files are copied byte for byte. The collector does
not select a few example cells. Missing or empty files stop collection; missing
runs are never silently dropped. For an intentional subset, add `--runs 194`
or a space-separated list. The separate regression campaign can be collected
with `--work .../hv44-delete-test --runs 194`; keep its provenance distinct.

## Transfer the output

The command prints the exact new `.tgz` and `.tgz.sha256` paths. SFTP both files
to the Mac. In their destination directory, verify the checksum using the
printed filename, for example:

```sh
shasum -a256 -c hv-histograms-EXAMPLE.tgz.sha256
```

Extract into a new directory. The archive contains `refine1/`, `refine2/`, a
manifest, and a copy of the collector. The default archive has 27 original
input files; event ROOT files from `final/` are not included.

The manifest records each source path, size, SHA-256, run, voltage and stage,
plus the host, collection timestamps and collector hash. Sources and copied
bytes are checked before archive publication. Each invocation uses a fresh
directory; prior inputs and outputs are preserved. A failure can leave partial
outputs for inspection. Only a successful exit with the printed checksum
sidecar indicates a completed collection.

The collector validates packaging and byte preservation, not ROOT contents or
the scientific quality of the calibrations. Campaign build provenance and
selection differences between voltages remain matters for the analysis.

## Tests

From this directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_collect_hv_histograms
```

The six tests use synthetic bytes and temporary directories. They cover the
complete file list, hashes and archive contents, missing and empty input
rejection, overwrite protection, source mutation detection, and explicit
subsets. They do not require ROOT or real detector data.
