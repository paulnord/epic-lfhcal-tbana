# Ari working analyzed folder

This organizer copies selected products from the verified November 11 archive into a **new** working folder beside raw data. It does not rerun analysis, submit jobs, move/delete old results, or merge into an existing destination.

## Included
The successful RF and other-settings product trees; original run302 conversion/calibration stages; newer run302 annotated waveform products. Existing stage names are retained: converted, pedestal, transfer, mip, selected, refine1–3, calibrated, waveform and plots. An empty comparisons directory is created for trend plots.

All 23 expected calibrated event files, waveform histogram files and measurement CSVs must be present. Run331/RF7 was absent from the archive and must be processed separately. Interrupted attempts, code/build/campaign copies, older run302 waveform products and later combined books are excluded. The original archive remains the preserved code/configuration record.

## Read-only plan (native tcsh)
Download the helper from this branch or a pinned commit. The following assumes it is named organize_ari.py in the current directory:

```tcsh
set archive = /gpfs01/star/pwg/pnord/eic/2026TBanalysis/ari-analysis-20261111T163523Z-2189737
set analyzed = /gpfs01/star/pwg/pnord/eic/2026TBdata/analyzed
python3 organize_ari.py --archive "$archive" --destination "$analyzed"
```

The plan prints file counts, GiB, coverage, exclusions and plan_sha256. No files or directories are created. The plan uses the exact archived file paths from metadata, checks sizes and refuses symlinks, missing products and conflicting destination names. It does not read/hash all large ROOT files at this stage.

Review the plan and applicable PWG quota. A filesystem free-space check is not a quota check.

## Copy after plan review

Use the exact plan hash printed above, replacing PASTE_PLAN_SHA256:

```tcsh
python3 organize_ari.py --archive "$archive" --destination "$analyzed" --copy --plan-sha256 PASTE_PLAN_SHA256 --quota-reviewed
```

If quota cannot be determined and you knowingly accept a possible partial copy, replace --quota-reviewed with --accept-unknown-quota. Do not use either flag without that review/decision. Use a site-appropriate execution node for a large transfer.

The destination must not exist. Every copied product is checked against its archived SHA256 and read back. A failure preserves its partial directory with INCOMPLETE; never delete/resume it blindly. Success writes IMPORT_BYTE_VERIFIED and removes only its own INCOMPLETE marker. No original file is changed.

The imported metadata records all source-to-destination mappings and checksums, as well as the original inventory. This is **byte verification, not ROOT-structure, scientific-validity or full-environment restorability certification**. Existing ROOT files should be opened/read by the plotting workflow before relying on them.

## Tests
```
python3 -m unittest -v test_organize_ari.py
```

Synthetic tests cover read-only planning, verified copy, tampering, destination collisions, identical duplicates, missing coverage, existing destinations, path traversal, symlinks, wrong plan hashes, and exclusion of interrupted/old302 waveform products. No BNL jobs or production data are used.
