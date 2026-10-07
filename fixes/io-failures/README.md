# Checked I/O fix for the PS rerun

Run `bash apply-and-build.sh ACTIVE_SOURCE EIC_SHELL` while the campaigns are
idle. The script checks and applies a targeted patch, then rebuilds Convert and
DataPrep in the existing build directory through the EIC shell. It accepts both
the original unchecked DataPrep and the version containing the earlier ROOT
write-bit check. It preserves the fitter, configurations, and all unrelated
source changes; an unrecognized layout fails without applying the patch.
There is no new runtime wrapper. The bundled run-in-eic-shell.sh is an unchanged
copy of the existing calibration shell launcher used for this one-time build.

A successful build prints `Checked I/O build ready`. Its checksum marker can
be checked with:

```sh
sha256sum --status -c "$LFHCAL_SOURCE/NewStructure/build/checked-io.sha256"
```

Afterwards create fresh campaigns from the existing PS Yallfiles and use
`yall-run start CAMPAIGN --overwrite`. This is a full restart, including
conversion and pedestal extraction, and replaces files at the existing output
paths. Do not run an old campaign or Legacy comparison against those paths
concurrently. `resume --overwrite` only reruns unfinished tasks and would keep
the false-success outputs from the quota incident.

The error handling is tested in `tests/io-failures`; it does not change the
calibration method or fit settings.
