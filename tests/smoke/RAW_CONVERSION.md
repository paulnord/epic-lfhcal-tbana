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

Observed with the current production code (review base `6be44e6`, ROOT 6.40):

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

Offline fixture integrity is included in unittest discovery and baseline CI;
**that does not mean real conversion passed**. Neither strict raw diagnostic is
called by the default smoke runner or the required CI gate. No production
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
