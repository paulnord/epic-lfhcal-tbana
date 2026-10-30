import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_ari_rf_plot_only.py"
SPEC = importlib.util.spec_from_file_location("prepare", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        (self.source / "configs/TB2026").mkdir(parents=True)
        (self.source / "configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv").write_text("fixture\n")
        (self.source / "tools").mkdir()
        (self.source / "tools/run-in-eic-shell.sh").write_text("fixture\n")
        self.shell = self.base / "eic-shell"
        self.shell.write_text("#!/bin/sh\nexit 0\n")
        self.shell.chmod(0o755)
        self.cal, self.hist = self.base / "cal.root", self.base / "hist.root"
        self.cal.write_bytes(b"calibration"); self.hist.write_bytes(b"histogram")
        self.inputs = self.base / "rf_inputs.txt"
        self.inputs.write_text("cal.root hist.root\n")
        self.output = self.base / "output"

    def prepare(self):
        with patch.object(MODULE.subprocess, "check_output", side_effect=lambda cmd, **kw: "" if "status" in cmd else "fixture-head\n"):
            return MODULE.prepare(self.inputs, self.output, self.shell, self.source)

    def test_prepare_does_not_submit_or_change_inputs(self):
        previous = [(p.read_bytes(), p.stat().st_mtime_ns) for p in (self.cal, self.hist, self.inputs)]
        job = self.prepare()
        self.assertIn("queue 1", job.read_text())
        self.assertEqual(previous, [(p.read_bytes(), p.stat().st_mtime_ns) for p in (self.cal, self.hist, self.inputs)])
        payload = (self.output / "payload.sh").read_text()
        self.assertIn("CompareWaveform", payload)
        self.assertNotIn("HGCROCStudy", payload)
        self.assertNotIn("condor_submit", payload)
        self.assertNotIn(" -f\n", payload)
        for script in ("payload.sh", "launch.sh"):
            subprocess.run(["bash", "-n", str(self.output / script)], check=True)
        env = dict(os.environ); env.pop("_CONDOR_JOB_AD", None)
        rejected = subprocess.run(["bash", str(self.output / "launch.sh")], env=env, capture_output=True)
        self.assertEqual(rejected.returncode, 2)

    def test_existing_output_refused(self):
        self.output.mkdir()
        with self.assertRaises(ValueError): self.prepare()

    def test_missing_input_refused_without_output(self):
        self.hist.unlink()
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists())

    def test_empty_input_list_refused(self):
        self.inputs.write_text("")
        with self.assertRaises(ValueError): self.prepare()

    def test_duplicate_pair_refused(self):
        self.inputs.write_text("cal.root hist.root\ncal.root hist.root\n")
        with self.assertRaises(ValueError): self.prepare()

    def test_input_mutation_detected(self):
        self.prepare()
        with patch.object(MODULE.subprocess, "check_output", side_effect=lambda cmd, **kw: "" if "status" in cmd else "fixture-head\n"):
            MODULE.verify(self.output / "inputs.json")
            self.hist.write_bytes(b"changed histogram")
            with self.assertRaises(ValueError): MODULE.verify(self.output / "inputs.json")

    def test_tracked_source_edit_detected(self):
        self.prepare()
        with patch.object(MODULE.subprocess, "check_output", side_effect=lambda cmd, **kw: " M source.cc\n" if "status" in cmd else "fixture-head\n"):
            with self.assertRaises(ValueError): MODULE.verify(self.output / "inputs.json")

    def test_source_head_change_detected(self):
        self.prepare()
        with patch.object(MODULE.subprocess, "check_output", return_value="different-head\n"):
            with self.assertRaises(ValueError): MODULE.verify(self.output / "inputs.json")


if __name__ == "__main__": unittest.main()
