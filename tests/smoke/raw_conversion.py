#!/usr/bin/env python3
"""Strict, bounded CAEN v3.3 conversion checks; no real beam data or fitting."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# Synthetic records in the documented production CAEN v3.3 format. Two mapped
# channels, two complete events; distinct values expose duplication/cross-talk.
RAW = """// File Format Version 3.3
// Run start time Thu Sep 05 12:00:00 2024
Brd Ch LG HG Tstamp_us TrgID NHits
0 0 11 101 1000 7 2
0 1 12 102
0 0 21 201 2000 8 2
0 1 22 202
"""
MAPPING = "0 0 0 synthetic 0 0 0 0 0 0 1\n0 1 1 synthetic 1 0 0 0 0 0 1\n"
RUNS = """year 2024
month 09
readout CAEN
facility synthetic
beam-line smoke
42,Muon,-13,5,44,41,50,50,0,0,20,25
"""


def inspect_output(library, filename):
    # Invoked in a fresh process: inspect actual serialized production trees,
    # not objects retained by Convert or a mock implementation.
    import ROOT
    ROOT.gSystem.AddDynamicPath(str(library.parent))
    if ROOT.gSystem.Load(str(library)) < 0:
        raise RuntimeError("cannot load production library")
    file = ROOT.TFile.Open(str(filename))
    if not file or file.IsZombie() or file.TestBit(ROOT.TFile.kRecovered):
        raise RuntimeError("missing/corrupt/recovered conversion output")
    trees = {name: file.Get(name) for name in ("Setup", "Calib", "Data")}
    if not all(trees.values()):
        raise RuntimeError("missing production Setup/Calib/Data tree")
    setup_tree, calib_tree, data = (trees[n] for n in ("Setup", "Calib", "Data"))
    setup_tree.GetEntry(0)
    setup = ROOT.Setup.GetInstance()
    setup.Initialize(setup_tree.setup)
    calib_tree.GetEntry(0)
    result = {"entries": {n: int(t.GetEntries()) for n, t in trees.items()},
              "mapping": [setup.GetCellID(0, i) for i in range(2)],
              "calibration_run": calib_tree.calib.GetRunNumber(), "events": []}
    for row in data:
        event = row.event
        result["events"].append({
            "id": event.GetEventID(), "run": event.GetRunNumber(),
            "time": event.GetTimeStamp(), "vop": event.GetVop(),
            "tiles": [[event.GetTile(i).GetCellID(), event.GetTile(i).GetADCLow(),
                       event.GetTile(i).GetADCHigh()] for i in range(event.GetNTiles())]})
    print("CAEN_RESULT=" + json.dumps(result))


class RawConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="caen-smoke-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        (self.work / "mapping.txt").write_text(MAPPING)
        (self.work / "runs.csv").write_text(RUNS)

    def convert(self, text):
        source = self.work / "Run42_synthetic.txt"
        source.write_text(text)
        self.output = self.work / "converted.root"
        return subprocess.run([str(BUILD / "Convert"), "-c", str(source),
                               "-m", str(self.work / "mapping.txt"),
                               "-r", str(self.work / "runs.csv"), "-o", str(self.output)],
                              cwd=self.work, capture_output=True, text=True, timeout=TIMEOUT)

    def assert_rejected(self, text, diagnostic):
        result = self.convert(text)
        log = result.stdout + result.stderr
        # A signal/crash is not acceptable rejection; neither is exit-zero
        # after printing an error. No recovery contract is assumed here.
        self.assertIn(diagnostic, log)
        self.assertGreater(result.returncode, 0, log)
        self.assertNotIn("segmentation violation", log.lower())

    def test_complete_events_and_round_trip(self):
        result = self.convert(RAW)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        read = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                               "--inspect", str(self.output), "--build-dir", str(BUILD)],
                              cwd=self.work, capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(read.returncode, 0, read.stdout + read.stderr)
        records = [line.removeprefix("CAEN_RESULT=") for line in read.stdout.splitlines()
                   if line.startswith("CAEN_RESULT=")]
        self.assertEqual(len(records), 1, read.stdout)
        saved = json.loads(records[0])
        with self.subTest(check="tree counts, no duplicated event"):
            self.assertEqual(saved["entries"], {"Setup": 1, "Calib": 1, "Data": 2})
        with self.subTest(check="mapping and metadata"):
            self.assertEqual(saved["mapping"], [0, 1])
            self.assertEqual(saved["calibration_run"], 42)
            self.assertEqual([e["id"] for e in saved["events"]], [7, 8])
        for index, expected in enumerate(([[0, 11, 101], [1, 12, 102]],
                                          [[0, 21, 201], [1, 22, 202]])):
            with self.subTest(event=index):
                event = saved["events"][index]
                self.assertEqual(event["run"], 42)
                self.assertEqual(event["vop"], 44.)
                self.assertEqual(event["tiles"], expected)
                self.assertTrue(math.isfinite(event["time"]), event)
                self.assertEqual(event["time"], (index + 1) * 1000.)

    def test_crlf_capture_is_accepted(self):
        result = self.convert(RAW.replace("\n", "\r\n"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unsupported_format_is_rejected(self):
        self.assert_rejected(RAW.replace("Version 3.3", "Version 9.9"),
                             "This version cannot be converted")

    def test_truncated_hit_is_rejected(self):
        self.assert_rejected(RAW.rsplit("0 1 22 202", 1)[0], "Expecting 4 fields")

    def test_short_event_header_is_rejected(self):
        self.assert_rejected(RAW.replace("0 0 11 101 1000 7 2", "0 0 11 101 1000 7"),
                             "Unexpected number of fields")

    def test_nonnumeric_adc_is_rejected(self):
        result = self.convert(RAW.replace("0 1 22 202", "0 1 22 BROKEN"))
        self.assertGreater(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("segmentation violation", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=15.)
    parser.add_argument("--inspect", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    BUILD, TIMEOUT = args.build_dir.resolve(), args.timeout
    if not math.isfinite(TIMEOUT) or TIMEOUT <= 0:
        parser.error("timeout must be finite and positive")
    if args.inspect:
        candidates = [BUILD / name for name in ("libLFHCAL.so", "libLFHCAL.dylib")]
        inspect_output(next(p for p in candidates if p.is_file()), args.inspect)
    else:
        unittest.main(argv=[sys.argv[0]], verbosity=2)
