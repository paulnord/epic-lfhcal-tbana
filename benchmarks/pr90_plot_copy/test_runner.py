#!/usr/bin/env python3
"""ROOT-free tests of orchestration safeguards, not tests of ROOT plotting."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import run_pr90_benchmark as bench


class RunnerTests(unittest.TestCase):
    def fixture(self, path):
        (path / "plot.png").write_bytes(b"fixture image bytes; not an actual ROOT plot")
        value = dict(elapsed_seconds=2.0, peak_rss_kib=204800,
                     before_digest="same", after_digest="same", saved_digest="same",
                     caller_unchanged=True, round_trip_unchanged=True, plot_file="plot.png")
        (path / "result.json").write_text(json.dumps(value))
        return value

    def test_result_and_median(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.fixture(path)
            base = bench.read_result(path, 4.0, "base", 1)
            pr = dict(base, variant="pr90", elapsed_seconds=1.0, peak_rss_kib=102400)
            result = bench.summarize([base, pr])
            self.assertTrue(result["semantic_digests_equal"])
            self.assertTrue(result["png_bytes_equal"])
            self.assertEqual(result["stats"]["plot_speedup_ratio"], 2.0)
            self.assertEqual(result["stats"]["median_peak_rss_reduction_mib"], 100.0)

    def test_semantic_mismatch_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.fixture(path)
            base = bench.read_result(path, 4.0, "base", 1)
            pr = dict(base, variant="pr90", saved_digest="different")
            self.assertFalse(bench.summarize([base, pr])["semantic_digests_equal"])

    def test_png_mismatch_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.fixture(path)
            base = bench.read_result(path, 4.0, "base", 1)
            pr = dict(base, variant="pr90", plot_sha256="different")
            self.assertFalse(bench.summarize([base, pr])["png_bytes_equal"])

    def test_invalid_results_rejected(self):
        changes = [dict(caller_unchanged=False), dict(after_digest="changed"),
                   dict(round_trip_unchanged=False), dict(elapsed_seconds=0),
                   dict(peak_rss_kib=-1), dict(plot_file="../outside.png")]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                value = self.fixture(path)
                value.update(change)
                (path / "result.json").write_text(json.dumps(value))
                with self.assertRaises(RuntimeError):
                    bench.read_result(path, 1, "base", 1)

    def test_missing_saved_digest_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            value = self.fixture(path)
            del value["saved_digest"]
            (path / "result.json").write_text(json.dumps(value))
            with self.assertRaises(RuntimeError):
                bench.read_result(path, 1, "base", 1)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "must not exist"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bench.main(["--dry-run", "--out", str(out)]), 0)
            self.assertFalse(out.exists())

    def test_resource_guard(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                bench.main(["--dry-run", "--cells", "129"])

    def test_checkout_and_exact_scope(self):
        # Use tiny local repositories to exercise real git without network,
        # without touching the project checkout, and with spaces in paths.
        with tempfile.TemporaryDirectory(prefix="pr90 test ") as directory:
            root = Path(directory)
            original = root / "original"
            original.mkdir()
            def git(*args):
                return subprocess.check_output(["git", "-C", str(original), *args],
                                               text=True, stderr=subprocess.DEVNULL).strip()
            git("init", "-q")
            for name in bench.SOURCE_FILES:
                file = original / name
                file.parent.mkdir(exist_ok=True)
                spacing = "  " if name.endswith(".cc") else "   "
                file.write_text(f"PlotCorr2DLayer({spacing}std::map<int,TileSpectra> spectra, int option, \n")
            git("add", ".")
            git("-c", "user.name=Local fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "base")
            base_sha = git("rev-parse", "HEAD")
            for name in bench.SOURCE_FILES:
                file = original / name
                file.write_text(file.read_text().replace("std::map<int,TileSpectra> spectra", "const std::map<int,TileSpectra>& spectra").replace("option, \n", "option,\n"))
            git("add", ".")
            git("-c", "user.name=Local fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "pr")
            pr_sha = git("rev-parse", "HEAD")
            (original / "untracked-work").write_text("must survive")
            before = git("status", "--porcelain")
            with contextlib.redirect_stdout(io.StringIO()):
                bench.checkout(str(original), base_sha, root / "base", root / "git.log")
                bench.checkout(str(original), pr_sha, root / "pr", root / "git.log")
            bench.verify_scope(root / "base", root / "pr")
            self.assertEqual(git("status", "--porcelain"), before)
            self.assertEqual(git("rev-parse", "HEAD"), pr_sha)
            self.assertEqual((original / "untracked-work").read_text(), "must survive")
            (root / "pr" / bench.SOURCE_FILES[0]).write_text("unexpected")
            with self.assertRaises(RuntimeError):
                bench.verify_scope(root / "base", root / "pr")


if __name__ == "__main__":
    unittest.main()
