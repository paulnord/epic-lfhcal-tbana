#!/usr/bin/env python3
"""Strict, currently failing real CAEN raw diagnostics; opt-in, outside CI gate."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from caen_fixture import FIXTURES, malformed_variants, parse_capture

# Test-only one-to-one geometry, not reconstructed physical detector geometry.
MAPPING = "".join(f"0 {channel} {cell} raw_fixture {cell} 0 0 0 0 0 1\n"
                  for cell, channel in enumerate((32, 33, 34)))
# Only the run number and bias are from capture/log metadata. Species, energy,
# breakdown voltage, geometry and other values here are test placeholders.
RUNS = """year 2025
month 06
readout CAEN
facility fixture
beam-line none
34,fixture,0,0,42.3,0,50,50,0,0,0,0
36,fixture,0,0,45,0,50,50,0,0,0,0
"""


class RealRawConversionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="caen-real-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        (self.work / "mapping.txt").write_text(MAPPING)
        (self.work / "runs.csv").write_text(RUNS)

    def convert(self, raw, run=34):
        source = self.work / f"Run{run}_fixture.txt"
        source.write_bytes(raw)
        self.output = self.work / "converted.root"
        # A separate output for each subtest; stale output cannot pass a check.
        if self.output.exists():
            self.output.unlink()
        return subprocess.run([str(BUILD / "Convert"), "-c", str(source),
                               "-m", str(self.work / "mapping.txt"),
                               "-r", str(self.work / "runs.csv"), "-o", str(self.output)],
                              cwd=self.work, capture_output=True, text=True, timeout=TIMEOUT)

    def inspect(self):
        read = subprocess.run([sys.executable, str(Path(__file__).with_name("raw_conversion.py")),
                               "--inspect", str(self.output), "--build-dir", str(BUILD),
                               "--channels", "32,33,34"], cwd=self.work, capture_output=True,
                              text=True, timeout=TIMEOUT)
        self.assertEqual(read.returncode, 0, read.stdout + read.stderr)
        records = [line.removeprefix("CAEN_RESULT=") for line in read.stdout.splitlines()
                   if line.startswith("CAEN_RESULT=")]
        self.assertEqual(len(records), 1, read.stdout)
        return json.loads(records[0])

    def check_round_trip(self, filename, run, bias):
        raw = (FIXTURES / filename).read_bytes()
        expected = parse_capture(raw)
        # Deliberate diagnostic derivative, NOT a claim original bytes worked.
        result = self.convert(raw.replace(b"\r\n", b"\n"), run)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        saved = self.inspect()
        with self.subTest(check="tree counts; no duplicate EOF event"):
            self.assertEqual(saved["entries"], {"Setup": 1, "Calib": 1, "Data": len(expected)})
        with self.subTest(check="one-to-one test mapping and run metadata"):
            self.assertEqual(saved["mapping"], [0, 1, 2])
            self.assertEqual(saved["calibration_run"], run)
            self.assertTrue(all(e["run"] == run for e in saved["events"]))
            # RunInfo stores bias as float before Event widens it to double.
            self.assertTrue(all(math.isclose(e["vop"], bias, rel_tol=0., abs_tol=1e-5)
                                for e in saved["events"]))
        with self.subTest(check="all trigger IDs, including recorded reset"):
            self.assertEqual([e["id"] for e in saved["events"]], [e["id"] for e in expected])
        with self.subTest(check="all measured ADCs and cell IDs"):
            self.assertEqual([e["tiles"] for e in saved["events"]], [e["tiles"] for e in expected])
        with self.subTest(check="finite single-board timestamps"):
            self.assertTrue(all(math.isfinite(e["time"]) for e in saved["events"]),
                            "nonfinite timestamp in serialized Data tree")
            self.assertEqual(len(saved["events"]), len(expected))
            for actual, reference in zip(saved["events"], expected):
                self.assertAlmostEqual(actual["time"], reference["time"], delta=1e-6)

    def test_original_crlf_captures_are_accepted(self):
        for name, run in (("Run34_first16.txt", 34), ("Run36_list.txt", 36)):
            with self.subTest(file=name):
                result = self.convert((FIXTURES / name).read_bytes(), run)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_run34_lf_diagnostic_round_trip(self):
        self.check_round_trip("Run34_first16.txt", 34, 42.3)

    def test_run36_lf_diagnostic_round_trip(self):
        # Acquisition-quality concerns must not be called malformed syntax.
        self.check_round_trip("Run36_list.txt", 36, 45.)

    def test_controlled_malformed_derivatives_are_rejected(self):
        diagnostics = {"unsupported_format": "This version cannot be converted",
                       "short_header": "Unexpected number of fields",
                       "truncated_hit": "Expecting 4 fields"}
        for name, raw in malformed_variants((FIXTURES / "Run34_first16.txt").read_bytes()).items():
            with self.subTest(variant=name):
                result = self.convert(raw)
                log = result.stdout + result.stderr
                if name in diagnostics:
                    self.assertIn(diagnostics[name], log)
                self.assertGreater(result.returncode, 0, log)
                self.assertNotIn("segmentation violation", log.lower())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--timeout", default=15., type=float)
    args = parser.parse_args()
    BUILD, TIMEOUT = args.build_dir.resolve(), args.timeout
    if not math.isfinite(TIMEOUT) or TIMEOUT <= 0:
        parser.error("timeout must be finite and positive")
    unittest.main(argv=[sys.argv[0]], verbosity=2)
