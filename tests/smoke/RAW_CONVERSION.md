# Optional raw-conversion diagnostic

Run in the build's ROOT/PyROOT environment:

```sh
python3 tests/smoke/raw_conversion.py --build-dir NewStructure/build
```

This is a strict diagnostic, **currently failing**, not part of the baseline
smoke pass or a required CI gate. It generates a 167-byte synthetic CAEN v3.3
text capture, a matching two-channel board-0 mapping, and one run-list row in a
temporary directory. No acquired/private data is included. Two complete events
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
- Unsupported version is correctly rejected with exit 1.

The tests preserve these strict expectations; no expected-failure decorations,
production fixes, or altered golden outputs hide the defects. The unconditional
EOF `TdataOut->Fill()`, division by maximum board index, and `return -1` from a
`bool` converter are relevant production sites to investigate separately.
