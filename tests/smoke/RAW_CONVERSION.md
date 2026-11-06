# Optional raw-conversion diagnostics

Run in the build's ROOT/PyROOT environment:

```sh
python3 tests/smoke/raw_conversion.py --build-dir NewStructure/build
python3 tests/smoke/real_raw_conversion.py --build-dir NewStructure/build
```

These are strict diagnostics, **currently failing**, not part of the baseline
smoke pass or a required CI gate. `raw_conversion.py` generates a 167-byte synthetic CAEN v3.3
text capture, a matching two-channel board-0 mapping, and one run-list row in a
temporary directory. Two complete synthetic events
have distinct event IDs and ADCs. Actual `Convert` output is reopened in a new
PyROOT process to check production Setup/Calib/Data trees, mapping, metadata,
ADC values, event counts, and timestamps. Every subprocess has a 15-second limit.

Deterministic corruptions target format version, a short event header, EOF
inside a declared hit block, and a nonnumeric ADC. There is no random seed or
recovery assumption: malformed input must fail explicitly, not crash, hang, or
silently succeed. This is CAEN-only, not HGCROC stream validation, DataPrep
calibration extraction, all workflow inputs/outputs, or a beam-data replay.

Historical observation (review base `6be44e6`, ROOT 6.40):

- Expected 2 events; output contains 3, with the last event duplicated.
- Expected finite timestamps 1000/2000; board-0-only mapping gives infinity.
- Short header and truncated hit print parser errors but incorrectly exit 0.
- Nonnumeric ADC is accepted instead of rejected.
- A valid CRLF version header is incorrectly rejected; LF input is accepted.
- Unsupported version is correctly rejected with exit 1.

The tests preserve these strict expectations; no expected-failure decorations,
production fixes, or altered golden outputs hide the defects. The unconditional
EOF `TdataOut->Fill()`, division by maximum board index, and `return -1` from a
`bool` converter are relevant production sites to investigate separately.

## Split scope and current base

This draft is independently based on main `9302328`; it does not depend on the
baseline smoke runner. The scripts, acquired bytes, manifest, and integrity
tests are preserved unchanged from combined PR #14 head `0810773`. Production
CAEN conversion code is unchanged from that tested head, so the failures below
remain known defects, not accepted expected results. No decoder repair or new
conversion feature is included. Historical results below are dated evidence,
not a claim that either strict command passed on this head.

## Real captures and deliberately malformed derivatives

`real_raw_conversion.py` uses two small, provenance-documented
[real CAEN fixtures](fixtures/caen/README.md): a byte-identical 16-event Run34
excerpt (2,220 bytes) and all of Run36 (62,192 bytes; 533 complete records).
The originals retain CRLF. Direct acceptance is checked separately from the
explicit LF-only diagnostic derivatives used to reach subsequent decoder paths.

Run36 is marked bad in the acquisition log because of a burst of triggers;
its complete records are not labeled parser corruption. The test preserves
its actual trigger-ID reset. Only deterministic, generated modifications to
Run34 are the malformed input tests. Test mapping/run-list placeholders do
not claim recovered physical geometry or a full calibrated replay.

Offline fixture integrity is checked separately in this draft:

```sh
python3 -m unittest discover -s tests/smoke -p 'test_raw_fixtures.py' -v
```

The `Diagnostic fixture integrity` workflow runs only these four offline tests
and Python syntax compilation. **A green result does not mean production
conversion or plotting passed.** Neither strict raw diagnostic runs in that
workflow; the baseline ROOT smoke suite is a separate PR. No production
source or golden expected result is changed to hide an existing failure.

### Real-fixture result, 2026-10-22

With unchanged production code from `8ce9024`, its pinned `h2g_decode`
`2a7f7d4`, and ROOT 6.40.00:

- Both original CRLF captures exit 1 with unsupported-version rejection.
- Explicit LF derivatives exit 0, but Run34 produces 17 entries instead of 16;
  Run36 produces 534 instead of 533. The last event is duplicated in both.
- Every expected prefix ID and ADC matches the source (including Run36's reset).
  All 17/534 saved timestamps are nonfinite with the single-board mapping.
- Three malformed derivatives (short header, truncated hit, nonnumeric ADC)
  incorrectly exit 0. Unsupported format is correctly rejected with exit 1.
- The strict real diagnostic exits 1: four test methods, 13 failing subchecks.
  Baseline smoke and all 15 offline runner/fixture tests pass separately.

This local build used the official PyPI ROOT 0.1a12 distribution (ROOT 6.40.00),
CMake 4.1.3 and GCC 14.2.0. ROOT's wheel needed local relocation symlinks and
an executable linker `-rpath-link` to its bundled `root.libs`; ROOT also warned
of a possible C++ standard-library version mismatch. Those environment-only
adjustments are not repository changes. The official ROOT 6.34 CI image remains
the separate baseline build check; it does not run these strict diagnostics.

### Recheck on the independent split base, 2026-10-26

With unchanged production sources from main `9302328`, decoder `2a7f7d4`,
ROOT 6.40.00, CMake 4.4.4 and GCC 14.2.0, both strict commands were rerun:

- Synthetic diagnostic: exit 1; 6 test methods, 8 failing subchecks.
- Acquired-fixture diagnostic: exit 1; 4 test methods, 13 failing subchecks.
- The same CRLF rejection, duplicate EOF event, nonfinite timestamp and
  malformed-input acceptance defects reproduced. Unsupported-format rejection
  still passed. No assertions, fixtures or expected results were weakened.
- The four offline fixture-integrity tests passed separately. The independent
  baseline smoke PR built `Convert`/`DataPrep` and passed its 11 runner tests
  and real ROOT write/read smoke; that does not validate conversion.

The reused ROOT wheel emitted its C++ standard-library compatibility warning.
This local run is distinct from the official-image ROOT CI in the smoke PR;
this diagnostic draft's CI is offline integrity/syntax only.
