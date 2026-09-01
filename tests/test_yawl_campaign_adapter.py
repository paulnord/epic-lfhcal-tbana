#!/usr/bin/env python3

import pathlib
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPOSITORY / "tools" / "make-tb2026-yawl-campaign"


class YawlCampaignAdapterTests(unittest.TestCase):
    def test_analysis_graph_renders_as_yawl_toml(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            manifest = work / "analysis.toml"
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--repository",
                    str(REPOSITORY),
                    "--raw-dir",
                    str(work / "raw"),
                    "--output-dir",
                    str(work / "analysis"),
                    "--pedestal-run",
                    "137",
                    "--muon-runs",
                    "138-149",
                    "--calibration-name",
                    "FullSetC_1",
                    "--bad-channels",
                    str(work / "bad-channels.txt"),
                    "--toa-offsets",
                    str(work / "toa-offsets.csv"),
                    "--manifest",
                    str(manifest),
                    "153",
                    "159",
                    "165",
                    "178",
                ],
                cwd=REPOSITORY,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            text = manifest.read_text()

        self.assertIn('[campaign]\nname = "tb2026-FullSetC_1"\nbackend = "condor"', text)
        self.assertIn("[condor]", text)
        self.assertIn(
            f'wrapper = "{REPOSITORY / "tools/run-in-eic-container.sh"}"',
            text,
        )
        self.assertEqual(text.count("[[task]]"), 36)
        self.assertIn('name = "transfer-calibration"', text)
        self.assertIn('parents = ["pedestal", "merge-muons"]', text)
        self.assertIn('name = "strip-calibration"', text)
        self.assertIn('role = "final_calibration"', text)
        self.assertIn('name = "waveform-153"', text)


if __name__ == "__main__":
    unittest.main()
