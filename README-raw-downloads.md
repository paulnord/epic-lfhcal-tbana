# PS-2026 and SPS parameter-scan raw downloads

Use `download_calibration_raw.py` for a shared collection of raw `.h2g` files,
with per-set manifests. The same command can acquire one set or all sets;
shared inputs are downloaded only once. Nothing is converted, fitted, or submitted.

## Scope

| Selection | Included data | Unique files |
| --- | --- | ---: |
| `ps` | Named PS/T10 April 2026 muon sets A1-I2: 77 muon runs and 15 pedestals | 92 |
| `sps-param` | SPS/H2 May 2026 parameter scans: 28 pedestal/muon pairs plus 3 extra conversion-recipe runs | 59 |
| `all` (default) | Both collections | 151 |

PS voltage/position scans and pion/hadron samples are outside this selection.
The SPS scan includes runs 294-310 and 328-369, not just the smaller selections
in the example scan Yallfiles. Different parameter-scan settings must remain
separate when subsequently fitting.

## Fetch and run on BNL (tcsh)

Requirements: Linux, Python 3.8+, `xrdfs` and `xrdcp` on PATH. If the XRootD
clients are unavailable on the submission host, run the Python commands inside
your existing EIC shell environment. No additional Python packages are needed.

```tcsh
set REPO = ~/my_eic_work_with_LFHCAL/epic-lfhcal-tf1convolution-benchmark
set RAW = /gpfs01/star/pwg/pnord/eic/2026TBanalysis/calibration-raw

git -C "$REPO" fetch origin codex/adaptive-langau-minimal && \
git -C "$REPO" show FETCH_HEAD:download_calibration_raw.py > /tmp/download_calibration_raw.py

# Check availability and report the total size, without copying raw files.
python3 /tmp/download_calibration_raw.py --out "$RAW" --check

# Download everything selected above (both campaigns).
python3 /tmp/download_calibration_raw.py --out "$RAW" --download
```

There is no fixed expected byte count until the server metadata is queried.
`--download` repeats the preflight itself, so `--check` is optional. Both commands
write a timestamped manifest. With neither option, the default is an offline plan.

For PS alone, a single set, or the SPS scans:

```tcsh
python3 /tmp/download_calibration_raw.py --out "$RAW" --sets ps --download
python3 /tmp/download_calibration_raw.py --out "$RAW" --sets ps-b2 --download
python3 /tmp/download_calibration_raw.py --out "$RAW" --sets sps-param --download
```

`--sets ps-a1 ps-a2` and comma-separated names are also supported. `--list`
lists all 20 selections without writing anything. Scan selectors are
`sps-param1`, `sps-param2`, and `sps-param3`, following Fredi's calibration recipe.

Run the same download command again after an interruption. The default is two
concurrent transfers and three attempts per file; adjust with `--jobs` and `--tries`.

## Use the earlier direct xrdcp workflow

The original `download_raw.tcsh` used `xrdcp SOURCE FILE.part` without an `xrdfs`
metadata preflight. A timeout from the new preflight does not establish that this
direct transfer also fails. To use the original transfer method with the new run
lists, add `--direct`:

```tcsh
python3 /tmp/download_calibration_raw.py --out "$RAW" --download --direct --tries 1
```

This calls plain `xrdcp` sequentially, shows its output/progress, uses the configured
source URLs (now `dtn2304.jlab.org:8443` by default), and stops at a failed file.
Set selection still works, e.g. `--sets ps-a1`. There is no required container
change if the current shell's `xrdcp` works.

Like the original script, direct mode skips existing nonempty files and starts
partial transfers over. It only replaces its own tracked `.direct.part` files;
partials from the normal mode are left alone. A final filename is created only
after `xrdcp` succeeds and produces a nonempty file. Failed partials are retained
until retrying. The number of attempts per file follows `--tries`; `--jobs` does
not affect this sequential mode.

Direct mode does not query remote sizes, precheck total storage, or compare
server checksums. Its report explicitly labels existing files as unverified and
records a local checksum for newly copied files. This is not proof of agreement
with a server checksum. It cannot be combined with `--recheck`; use the normal
`--download` mode later for remote size/checksum verification when metadata
queries work.

## If metadata queries time out

Stop an older check with Ctrl-C. A timeout does not establish that an input is
missing. The script now probes one file per selected campaign before the full
preflight and stops scheduling queries after any failure. In-flight queries can
still take up to the configured timeout. Captured client diagnostics are retained
in the error, and the selected `xrdfs` executable is printed.

Use the small probe to compare the host's client with the EIC shell client:

```tcsh
python3 /tmp/download_calibration_raw.py --out "$RAW" --probe --query-timeout 20
~/my_eic_work_with_LFHCAL/eic-shell
```

After the EIC shell prompt appears, use the full path because the outer tcsh
variable is not exported to the inner shell:

```sh
python3 /tmp/download_calibration_raw.py \
  --out /gpfs01/star/pwg/pnord/eic/2026TBanalysis/calibration-raw \
  --probe --query-timeout 20
```

`--probe` reads size/checksum metadata for just the first file in each selected
campaign. It neither downloads data nor checks the rest of the list. Once it
succeeds, replace `--probe --query-timeout 20` with `--check` or `--download`.
If it also times out inside the EIC shell, retain its output for diagnosis of
network/server access. The script does not assume a server outage or silently
substitute another host or dataset.

## Files and verification

- PS files go under `ps-2026/raw/`; SPS files under `sps-2026/raw/`. Overlapping run
  numbers cannot overwrite the other campaign's data.
- `manifests/<timestamp>/` contains the complete plan, individual set JSON files,
  server sizes/checksums, transfer logs, and the final success/failure report.
- Every selected remote file must pass the size/checksum preflight before any
  raw transfer starts. Failed preflights record which inputs remain unchecked.
  `--check` does not verify existing local data.
- Downloads use `.part` files and resume with `xrdcp --continue`. A sidecar records
  which source and checksum the partial belongs to.
- A completed file is published only after whole-file size and checksum checks
  agree with the server. An existing file without a verification receipt is
  checked and adopted if it matches; an existing corrupt file is preserved and
  reported, never overwritten automatically.
- Unchanged files with matching source metadata and verification receipts are
  skipped. `--recheck` forces a complete reread of those local files.
- Per-file locks prevent simultaneous instances from writing the same file.
  A competing invocation reports a failure for the locked file; rerun afterward.
- Free space is checked, but filesystem free space is not a user quota check.
  Any missing, unreadable, or mismatching input gives a nonzero exit status.

If a corrupt or untracked partial is reported, inspect it and move it aside
before retrying; the downloader intentionally does not discard it automatically.
All verification receipts and manifests are small compared with the raw data.

## Pedestal associations retained for review

Collecting a pedestal does not approve its use for calibration. Per-set manifests
distinguish explicit script assignments from associations inferred from the run
database and nearby recipes.

| PS set | Pedestal included | Evidence / caveat |
| --- | ---: | --- |
| A1 | 85 | Inferred |
| A2 | 120 | Inferred |
| B1, B2 | 215 | Inferred; B1 muons have mixed dead times |
| C1 | 130 | Script assigned; mixed dead times |
| C2 | 171 | Script assigned; pedestal/muon dead times differ |
| D1 | 238, plus 265 for review | Script assigns 238, but CC differs; no replacement selected |
| D2 | 265 | Script assigned |
| E1 | 287 | Script assigned |
| E2 | 315 | Script assigned |
| F1 | 338 | Inferred |
| F2 | 366 | Inferred; muons labelled beam shutter open |
| G1 | 379, plus 404 for review | Inferred 379 has different CC; no replacement selected |
| G2 | 404 | Inferred |
| H1, I1 | 425 | Same listed muon inputs; recipe merge/board inconsistencies remain |
| I2 | 462 | Inferred; muons 463/464 appear in comments without an active I2 merge |

Run 191 is included for B1 because it appears in the merge list, despite being
omitted from the active conversion list. H1/I1 share their raw files; they are
not counted twice. The additional D1/G1 review pedestals are already needed by
D2/G2 when downloading the full collection.

SPS runs 297, 365, and 368 are in the parameter-scan conversion list but lack
explicit calibration pairs. They are retained as extra raw inputs. Run 368 has
CC=4 while pedestal 367 has CC=3; no association is invented for it.

## Sources and tests

The catalog is pinned to source commit
`5227c3e714e3be16b21a24bb76a99ecb8e85a2a5` in
[`paulnord/epic-lfhcal-tbana`](https://github.com/paulnord/epic-lfhcal-tbana/tree/5227c3e714e3be16b21a24bb76a99ecb8e85a2a5):

- `NewStructure/convertDataHGCROC_TBPST10_2026.sh`
- `NewStructure/runHGCROCCalibration_TBPST10_2026.sh`
- `NewStructure/convertDataHGCROC_TBSPSH2_2026.sh`
- `NewStructure/runHGCROCCalibration_TBSPSH2_2026.sh`
- The corresponding PS and SPS data-taking CSV databases.

The logical raw-data locations come from
[Fredi's data-access documentation](https://friederikebock.gitbook.io/epiclfhcaltb-ana/tb-analysis-basics/getting-the-data).
The default access route now uses JLab's `dtn2304.jlab.org:8443` work export:

```text
root://dtn2304.jlab.org:8443//jlab-osdf-ro/eic/EPIC/work/TestBeam/LFHCAL/CERN/2026/2026_PST10/raw/Run085.h2g
root://dtn2304.jlab.org:8443//jlab-osdf-ro/eic/EPIC/work/TestBeam/LFHCAL/CERN/2026/2026_SPSH2/raw/Run294.h2g
```

On 2026-10-06, Paul confirmed readable `xrdfs stat` responses from BNL for PS
Run085 (90,661,002 bytes) and SPS Run126 (353,078,209 bytes) under these roots.
The earlier `dtn-eic.jlab.org:1094` route timed out from BNL and his Mac.
This confirms sample metadata access, not availability of every requested file
or successful transfers/checksums. The new route was discovered by listing the
export; it is not a change to the run catalog or the local destination layout.
The separate `volatile/TestBeam/LFHCal` export is not used: PS Run085 existed
there, but SPS Run126 was absent.

Use normal `--download --query-timeout 20 --tries 1` to preflight and verify the
requested files on the new route. It leaves any old `.direct.part` files alone.
Direct mode deliberately refuses to overwrite a partial belonging to a different
source URL; preserve/move that partial and its JSON marker if choosing direct mode
after changing sources.

Directory overrides are available with `--ps-source` and `--sps-source`.

The metadata preflight accepts either Adler-32 or MD5, as named in the server's
checksum response. Local verification uses that same algorithm, and manifests,
partial markers, and verification receipts retain its name and value. The new
endpoint returned MD5 for PS Run085 on 2026-10-06. Unsupported algorithms and
malformed digests stop preflight; verification is never silently skipped.
Existing Adler-32 receipts and partial markers retain their original format.

Offline integration tests use simulated XRootD clients to exercise manifest
deduplication, campaign separation, preflight failures, interrupted transfers,
checksum verification, receipt reuse, and preservation of corrupt files:

```sh
python3 -m unittest -v test_download_calibration_raw
```

No live JLab transfer was performed in the development environment. The BNL
`--check` command establishes current remote availability and sizes.
