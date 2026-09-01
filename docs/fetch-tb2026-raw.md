# Fetching TB2026 raw HGCROC files

`tools/fetch-tb2026-raw` downloads selected `RunNNN.h2g` files from the
TB2026 SPS H2 directory in the JLab XRootD store. It requires Python 3 and
`xrdcp`; no EIC container is required for the transfer.

## Quick start

From the repository root, preview the FullSetC calibration and 50 GeV test
sample without downloading anything:

```console
python3 tools/fetch-tb2026-raw \
  --dry-run \
  --destination /gpfs01/star/pwg/pnord/eic/2026TBdata \
  137 138-149 153 159 165 178
```

Remove `--dry-run` to perform the downloads:

```console
python3 tools/fetch-tb2026-raw \
  --destination /gpfs01/star/pwg/pnord/eic/2026TBdata \
  137 138-149 153 159 165 178
```

A run specification may be one number or an inclusive ascending range.
Specifications can be mixed, and duplicate run numbers are downloaded only
once while retaining their first-listed order.

## Existing and partial files

For a destination that does not exist, the tool starts a normal `xrdcp`.
For an existing destination, it uses `xrdcp --continue` to resume a partial
copy. Use `--force` only when an existing file should be replaced and
downloaded again from the beginning.

The command stops at the first failed transfer and returns the `xrdcp` exit
status. Repeating the same invocation resumes any destination files left by an
interrupted transfer.

## Inspecting the remote directory

`xrdcp` copies files; `xrdfs` lists and inspects the remote store:

```console
xrdfs root://dtn-eic.jlab.org:1094 ls -l \
  /work/eic3/EPIC/TestBeam/LFHCAL/CERN/2026/2026_SPSH2/raw
```

To show only the FullSetC files used in the example:

```console
xrdfs root://dtn-eic.jlab.org:1094 ls -l \
  /work/eic3/EPIC/TestBeam/LFHCAL/CERN/2026/2026_SPSH2/raw \
  | grep -E '/Run(137|13[89]|14[0-9]|153|159|165|178)\.h2g$'
```

## Other sources and destinations

The default source is:

```text
root://dtn-eic.jlab.org:1094//work/eic3/EPIC/TestBeam/LFHCAL/CERN/2026/2026_SPSH2/raw
```

Use `--source` for another XRootD directory, `--destination` (or `-d`) for
another local directory, and `--xrdcp` when the executable is not available
as `xrdcp` on `PATH`. Run `python3 tools/fetch-tb2026-raw --help` for the
complete command-line reference.
