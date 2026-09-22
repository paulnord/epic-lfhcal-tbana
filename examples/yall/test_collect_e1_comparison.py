import contextlib
import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from collect_e1_comparison import campaign_inputs, collect


class CollectComparisonTest(unittest.TestCase):
    def fixture(self, base, label):
        work = base / (label + " work")
        campaign = work / "campaigns" / "campaign with spaces"
        results = work / "fullset-e1-repro"
        files = {
            work / "after-mip-setup.json": b'{"previous": "/input"}',
            campaign / "refine5_attempt_001/stdout.log": b"completed\n",
            campaign / "refine5_attempt_001/attempt.json": b'{"exit_code": 0}',
            results / "skim-check/selection.json": b'{"passed": true}',
            results / "final/calib_Final_Muon_FullSetE_1_calib.txt": b"calibration\n",
            results / "selected/events.root": b"EXCLUDE event tree",
            results / "plots/refine5/plot.pdf": b"EXCLUDE plot",
            work / "campaigns/unrelated/stdout.log": b"EXCLUDE other campaign",
        }
        for stage in range(1, 6):
            files[results / f"refine{stage}/test_Hists.root"] = b"histogram"
            files[results / f"refine{stage}/test_calib.txt"] = b"calibration"
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        (results / "external.txt").symlink_to(campaign / "refine5_attempt_001/stdout.log")
        return campaign, files

    def test_archive_and_checksum_preserve_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            x, xf = self.fixture(base, "X")
            m, mf = self.fixture(base, "M")
            with patch("collect_e1_comparison.checkout_info", return_value="revision\n"):
                with contextlib.redirect_stdout(io.StringIO()):
                    archive, checksum = collect(x, m, base)
            with tarfile.open(archive) as tar:
                names = tar.getnames()
                self.assertEqual(len(names), 31)
                for label in ("fixed-X", "muon-M"):
                    self.assertIn(f"{label}/after-mip-setup.json", names)
                    self.assertIn(f"{label}/fullset-e1-repro/refine5/test_Hists.root", names)
                    self.assertIn(f"{label}/fullset-e1-repro/skim-check/selection.json", names)
                    self.assertIn(f"{label}/campaigns/campaign with spaces/refine5_attempt_001/stdout.log", names)
                self.assertFalse(any("events.root" in n or "plot.pdf" in n or
                                     "unrelated" in n or "external.txt" in n for n in names))
                self.assertEqual(tar.extractfile("fixed-X/fullset-e1-repro/refine5/test_Hists.root").read(), b"histogram")
            self.assertEqual(checksum.read_text(),
                             hashlib.sha256(archive.read_bytes()).hexdigest() + "  E1-X-vs-M.tgz\n")
            for path, content in {**xf, **mf}.items():
                self.assertEqual(path.read_bytes(), content)

    def test_incomplete_and_duplicate_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            campaign, _ = self.fixture(base, "X")
            with self.assertRaisesRegex(ValueError, "different"):
                collect(campaign, campaign, base)
            (campaign.parent.parent / "fullset-e1-repro/refine5/test_Hists.root").unlink()
            with self.assertRaisesRegex(ValueError, "Missing histograms"):
                campaign_inputs(campaign)
            self.assertFalse(list(base.glob("e1-comparison-*")))


if __name__ == "__main__":
    unittest.main()
