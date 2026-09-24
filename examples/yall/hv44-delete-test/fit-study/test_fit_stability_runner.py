#!/usr/bin/env python3
"""Regression tests for frozen setup, safe perturbations, and failed processes."""
import json
from pathlib import Path
import tempfile
import unittest

import run_fit_stability as runner


class StabilityRunnerTest(unittest.TestCase):
    def setUp(self):
        self.base = {key: "1" for key in runner.FROZEN}
        for p, value in zip(runner.PARAMETERS, (3, 15, 10000, 1)):
            self.base.update({f"start_{p}": str(value), f"{p}_low": "0.01", f"{p}_high": "50000"})
        self.base.update(fit_status="4", integrator="fixed", fit_option="QRLMN0")

    def test_all_starts_change_only_one_parameter_and_never_setup(self):
        for name, spec in runner.STARTS.items():
            row = dict(self.base, integrator="adaptive")
            values = runner.start_values(self.base, name)
            for p, value in values.items():
                row[f"start_{p}"] = repr(value)
            runner.verify_setup(row, self.base, "adaptive", name, "QRLMN0")
            changed = [p for p in runner.PARAMETERS if values[p] != float(self.base[f"start_{p}"])]
            self.assertEqual(changed, [spec[0]] if spec else [])
        for key in runner.FROZEN:
            changed = dict(self.base)
            changed[key] = str(float(changed[key]) + 0.001)
            with self.assertRaisesRegex(ValueError, "frozen setup changed"):
                runner.verify_setup(changed, self.base, "fixed", "base", "QRLMN0")

    def test_start_cannot_be_clipped_to_boundary(self):
        self.base["width_high"] = "3.6"
        # Use the exact computed floating-point boundary.
        self.base["width_high"] = repr(3 * 1.2)
        with self.assertRaisesRegex(ValueError, "strictly interior"):
            runner.start_values(self.base, "width_hi")
        self.base["start_width"] = "nan"
        with self.assertRaises(ValueError):
            runner.start_values(self.base, "base")

    def test_process_failure_keeps_log_and_returncode(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "fits" / "case").mkdir(parents=True)
            fake = out / "fake-fitter"
            fake.write_text("#!/bin/sh\necho deliberate-failure\nexit 7\n")
            fake.chmod(0o700)
            case = dict(case_id="case", input="source.root", hist_key="hist", calib="calib.txt", cell_id=42, layers=5, vov=3.7)
            result = runner.run_one(fake, case, "fixed", "base", None, out, "QRLMN0")
            self.assertEqual(result["returncode"], 7)
            self.assertFalse(result["setup_verified"])
            self.assertIn("fitter process failed", result["automation_error"])
            self.assertEqual(Path(result["paths"]["log"]).read_text(), "deliberate-failure\n")
            self.assertIn("log", result["output_sha256"])
            # Existing logs/results cannot be overwritten.
            again = runner.run_one(fake, case, "fixed", "base", None, out, "QRLMN0")
            self.assertIsNone(again["returncode"])
            self.assertIn("File exists", again["automation_error"])

    def test_no_path_escape_or_duplicate_case(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "cases.json"
            case = dict(case_id="../escape", input=__file__, hist_key="h", calib=__file__, cell_id=1, layers=5, vov=3.7)
            source.write_text(json.dumps([case]))
            with self.assertRaisesRegex(ValueError, "unsafe or duplicate"):
                runner.load_cases(source)
            case["case_id"] = "ok"
            source.write_text(json.dumps([case, case]))
            with self.assertRaisesRegex(ValueError, "unsafe or duplicate"):
                runner.load_cases(source)


if __name__ == "__main__":
    unittest.main()
