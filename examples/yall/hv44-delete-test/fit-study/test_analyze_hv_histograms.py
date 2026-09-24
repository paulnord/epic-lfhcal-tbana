"""Synthetic ROOT fixtures for read-only inventory; no fitting or event simulation."""
import contextlib
import csv
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import ROOT
import analyze_hv_histograms as analyzer

ROOT.gROOT.SetBatch(True)


class Tests(unittest.TestCase):
    def fixture(self, work, run=194):
        hist_path, calib_path, preceding = analyzer.source_paths(work, run)
        hist_path.parent.mkdir(parents=True, exist_ok=True)
        preceding.parent.mkdir(parents=True, exist_ok=True)
        header = f"# Synthetic fixture, not BNL data\nRunNr: {run} Vop: 44 Vov: 5.7\n"
        lines = []
        for cid, bc in ((1, 3), (2, 3), (3, 3), (4, 1), (5, 3)):
            values = [cid, cid-1, 0, 0, 0, 80, .6, 80, .2, 50, 30, -1000, -1000, -64, -1000, -64, 270, bc]
            lines.append(" ".join(map(str, values)))
        calib_path.write_text(header + "\n".join(lines) + "\n")
        preceding.write_text(calib_path.read_text())
        file = ROOT.TFile(str(hist_path), "RECREATE")
        directory = file.mkdir("IndividualCellsTrigg")
        directory.cd()
        keep = []
        for cid, positions in ((1, [-1., .5, 1.5, 6.]), (2, []), (4, [.5]*8), (5, [.5]*500)):
            hist = ROOT.TH1D(f"hspectramipTriggADCCellID{cid}", "Synthetic fixture", 5, 0, 5)
            for x in positions:
                hist.Fill(x)
            if cid == 1:
                hist.SetBinError(2, math.nan)
            hist.Write()
            keep.append(hist)
        function = ROOT.TF1("fmipmipTriggHGCellID1", "[0]+[1]*x", .2, 4.)
        function.SetParameters(1., 2.)
        function.SetParLimits(0, .1, 10.)
        function.Write()
        file.Close()
        return hist_path, calib_path, preceding

    def test_inventory_plots_preservation_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            paths = self.fixture(work)
            hashes = {str(p.resolve()): analyzer.digest(p) for p in paths}
            with contextlib.redirect_stdout(io.StringIO()):
                result = analyzer.analyze(work, [194], work/"out", ROOT)
            self.assertEqual(result["input_sha256"], hashes)
            self.assertEqual(hashes, {str(p.resolve()): analyzer.digest(p) for p in paths})
            s = result["runs"][0]["summary"]
            self.assertEqual((s["calibration_cells"], s["present_histograms"], s["comparison_population"]), (5, 4, 3))
            self.assertEqual(s["missing_unmasked_histograms"], 1)
            self.assertEqual(s["zero_entry_unmasked"], 1)
            self.assertEqual((s["minimum"], s["median"], s["maximum"]), (0, 4, 500))
            self.assertEqual(s["counts_at_least"], {"200": 1, "500": 1, "1000": 0, "2000": 0, "5000": 0})
            self.assertEqual(s["nonfinite_error_cells"], 1)
            with (work/"out/cells.csv").open() as stream:
                rows = {int(r["cell_id"]): r for r in csv.DictReader(stream)}
            self.assertEqual((rows[1]["entries"], rows[1]["integral"], rows[1]["underflow"], rows[1]["overflow"]), ("4.0", "2.0", "1.0", "1.0"))
            self.assertEqual(rows[3]["entries"], "nan")
            self.assertEqual(rows[2]["entries"], "0.0")
            self.assertEqual(rows[4]["bc"], "1")
            function = result["runs"][0]["stored_functions"]["1"]
            self.assertEqual(function["parameters"][0]["low"], .1)
            self.assertEqual(function["parameters"][0]["high"], 10.)
            self.assertEqual(function["xmin"], .2)
            self.assertEqual(result["runs"][0]["calibration_metadata"]["Vop"], "44")
            self.assertIsNotNone(result["runs"][0]["preceding_calibration"])
            for name in result["plots"]:
                self.assertGreater((work/"out"/name).stat().st_size, 1000)
            json.loads((work/"out/summary.json").read_text())
            with self.assertRaisesRegex(ValueError, "output already exists"):
                analyzer.analyze(work, [194], work/"out", ROOT)

    def test_input_mutation_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            _, calib, _ = self.fixture(work)
            def mutate(*args):
                calib.write_text(calib.read_text() + "# Intentional test mutation\n")
                return []
            with mock.patch.object(analyzer, "plots", side_effect=mutate):
                with self.assertRaisesRegex(RuntimeError, "input changed"):
                    analyzer.analyze(work, [194], work/"out", ROOT)
            self.assertFalse((work/"out/summary.json").exists())
            self.assertTrue((work/"out/input-mutation.json").is_file())

    def test_missing_run_fails_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self.fixture(work)
            with self.assertRaisesRegex(ValueError, "missing input for run 195"):
                analyzer.analyze(work, [194, 195], work/"out", ROOT)
            self.assertFalse((work/"out").exists())

    def test_across_runs_missing_calib_and_geometry(self):
        rows = [dict(run=194, cell_id=1, module=0, layer=0, row=0, column=0,
                     bc=3, has_histogram=True, entries=0),
                dict(run=195, cell_id=1, module=0, layer=1, row=0, column=0,
                     bc=3, has_histogram=False, entries=math.nan),
                dict(run=195, cell_id=2, module=0, layer=0, row=0, column=1,
                     bc=1, has_histogram=True, entries=10)]
        compared = analyzer.compare_runs(rows, [194, 195])
        self.assertFalse(compared[0]["geometry_consistent"])
        self.assertTrue(compared[0]["run195_has_calibration"])
        self.assertFalse(compared[0]["run195_has_histogram"])
        self.assertEqual(compared[0]["run194_entries"], 0)
        self.assertFalse(compared[1]["run194_has_calibration"])
        self.assertTrue(math.isnan(compared[1]["run194_entries"]))

    def test_invalid_calibration_duplicate_and_field_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            _, calib, _ = self.fixture(work)
            original = calib.read_text()
            calib.write_text(original + original.splitlines()[-1] + "\n")
            with self.assertRaisesRegex(ValueError, "duplicate cell"):
                analyzer.read_calibration(calib)
            calib.write_text("1 2 3\n")
            with self.assertRaisesRegex(ValueError, "expected 18"):
                analyzer.read_calibration(calib)


if __name__ == "__main__":
    unittest.main()
