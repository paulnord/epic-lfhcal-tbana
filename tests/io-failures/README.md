# I/O failure propagation test

The PS calibration logs contained ROOT write errors (`Disk quota exceeded`) in
jobs that returned exit 0. DataPrep on `codex/adaptive-langau-minimal` discarded
`Analyses::Process()`'s result. The earlier DataPrep check exists on
`codex/adaptive-fit-module`, but Convert still discarded the result there.
Calibration text streams also did not check open/write/close failures, and ten
analysis paths ignored failed histogram-file creation.

The fix uses the same exit-status handling for DataPrep and Convert. It checks
the Process result, closes and checks their three ROOT output pointers, and
remembers error-level ROOT I/O/graphics diagnostics. The latter covers image
writers whose API returns void. It leaves the existing error handler installed
for printing/abort behavior, restores it on exit from the scope, and does not
treat fit-only errors or ordinary warnings as output failures. Calibration text
streams now throw on failure; the command-line boundary reports the exception
and exits 1. Failed histogram-file creation returns false immediately.

## Tests performed

GCC 13.3, ROOT 6.40.00, Linux. `run_fixture.py` compiled the real before/after
DataPrep.cc and Convert.cc entry points and real Calib.cc implementation. Only
Analyses::CheckAndOpenIO and Analyses::Process were replaced by fault-injection
fixtures. ROOT itself handled the injected writes; the tests did not just match
log strings. The actual modified Analyses.cc also passed a syntax-only compile.

Both patched executables returned 1 for:

- Failed input check and a false Process result.
- A TFile SysWrite quota failure (`EDQUOT`).
- A short TFile write.
- A ROOT write failure during final close after Process returned true.
- Writing calibration text to `/dev/full` and failure to open a text output.
- A real failed PNG SaveAs to a nonexistent directory.

Both returned 0 for healthy ROOT/text output, a normal warning, and a fit-only
error diagnostic. Healthy before/after ROOT files reopened without recovery and
contained the expected histogram entry/bin content. The baseline returned 0 for
Process=false, quota errors, short writes, text failures, and image failures;
the close-failure baseline terminated by signal. Results are in
`results-root-6.40.00.json` (44 invocations total, 22 after the fix).

This is an exit-status/I/O test. It does not rerun detector conversion, event
selection, or fits on BNL data. The fitter and numerical settings are unchanged.
The cluster build uses its own ROOT/compiler/decoder through the EIC shell.

To repeat against a checkout (baseline optional):

```sh
python3 tests/io-failures/run_fixture.py \
    --source NewStructure --root "$(root-config --prefix)" --out /tmp/lfhcal-io-tests
```

For comparison, `--baseline DIR` accepts a directory with the earlier
DataPrep.cc, Convert.cc, Analyses.h, and Calib.cc. Unchanged core dependencies
are read from --source.
