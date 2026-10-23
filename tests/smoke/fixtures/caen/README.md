# Small real CAEN captures

These are acquired CAEN DT5202 / Janus 3.6.0 spectroscopy ASCII exports (format
3.3), not synthetic events, HGCROC data, or a full beam/calibration campaign.
Only 64,412 raw bytes are committed. Both files retain original CRLF line
endings, spaces, ADCs, timestamps and trigger IDs. `.gitattributes` prevents Git
newline conversion. Tests never need network access.

## Source and extraction

`manifest.json` records the source URL, full-source SHA256/byte count, fixture
SHA256/byte count, extraction bounds and complete-event counts. Retrieved from
the linked Drive copies on 2026-10-22. The owner approved including small
captures in this public fork; that approval does not establish a license for
other datasets. No public JLab download URL has been verified for these copies.

- `Run34_first16.txt`: 2,220-byte, byte-identical prefix of
  [Run34_list.txt](https://drive.google.com/file/d/1IJ7Vg-f5urfF0s8ejvZtds22Gl2-SQDv/view).
  The original is 2,320,132 bytes and contains 19,998 complete events. The fixture
  is its nine header lines and first 16 complete three-hit events (57 lines).
  This is an excerpt of a short run, not the whole acquisition.
- `Run36_list.txt`: the entire 62,192-byte
  [original file](https://drive.google.com/file/d/1cqLhoogSc2_qVWZohkEeHtpOdizb2nQN/view),
  with 533 complete three-hit events (1,608 lines). It is an acquisition-quality
  edge case, **not** a deliberately corrupted file or a clean physics reference.

To reproduce Run34 after obtaining the source, verify its full hash against the
manifest, then use `source.read_bytes()[:2220]` and verify the fixture hash. The
cut is after the third hit of event 16, not inside a record. Run36 is copied in
full with no transformations. Neither source is downloaded by the test runner.

## Acquisition context and the word "bad"

The [Valpo Test Stand Run Log](https://docs.google.com/spreadsheets/d/1e_dAfmDfeCu7hy7HfBIGg53davKSqPpX5aU_yJ2J0j0/edit)
labels Run34 **good**, mC Sr90, June 23, 2025, 42.3 V, 1.976 s, OR-64, HG/LG
shaping 87.5 ns. Its listed count of 20,000 is not the raw file's 19,998 records.
The capture header starts at 17:10:28 UTC.

Run36 is labeled **bad**, Cosmic, June 23, 2025, 45 V, 97 s, count 21, with the
note: "3 tiles stacked, Majority trigger 2 - weird burst of triggers, try again".
The [matching acquisition-info file](https://drive.google.com/file/d/1u8xMs1Nx3YsBAjO-4j5XUoPdmAjNhSDb/view)
reports 97.329 s, DT5202, TLOGIC / MAJ64 majority 2 and TRIGGER_CNT (all triggers,
accepted or not). The capture header starts at 20:04:51 UTC. There are 533 raw
records, not 21: trigger IDs start at 17,261,297 and reset from 17,320,577 to 0
between records 511 and 512 (1-based), then finish at 21. Timestamps increase
throughout. The observed reset does not by itself establish its cause. Do not
confuse the run-log quality label with parser corruption or use the final
trigger ID as an event count.

Both captures contain board 0, channels 32, 33 and 34. The test supplies a
one-to-one geometry mapping to cell IDs 0, 1 and 2. That mapping and the run-list
placeholders are test scaffolding, not recovered physical geometry/calibration.

## What is tested

`test_raw_fixtures.py` checks hashes, byte counts, CRLF preservation, complete
record structure, sample values and Run36's recorded reset without ROOT.
This validates the test inputs, **not the production decoder**.

`real_raw_conversion.py` separately runs the production Convert executable and
reopens its serialized output in a fresh PyROOT process. Original CRLF acceptance
is tested directly. Explicitly labeled LF-normalized derivatives then exercise
all recorded IDs, ADC values, mapping, run metadata, counts and finite timestamps
past the known CRLF rejection. Original fixture files are never rewritten.

Four deterministic malformed derivatives of Run34's first two events test an
unsupported version, a short event header, EOF inside a hit block and nonnumeric
ADC. Only these generated derivatives are corrupted. They use LF so the CRLF
bug cannot make malformed validation falsely appear to pass. Expected behavior
is a positive nonzero exit, never a signal/crash, timeout or silent success.
The independent Python parser is a narrow fixture oracle, not a production
replacement or a specification for all CAEN modes.
