#!/usr/bin/env python3
"""ROOT-free orchestration checks, not physics/ROOT correctness tests."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_real_data as real


class RealDataTests(unittest.TestCase):
    def config(self, root):
        data = root / "data with spaces.root"
        runs = root / "runlist.txt"
        data.write_bytes(b"fixture, not a ROOT file")
        runs.write_text("fixture, not a real runlist\n")
        return real.waveform_config(data, runs, None, 1000)

    def outputs(self, root, payload=b"fixture pixels"):
        (root / "plots").mkdir()
        (root / "analysis_Hists.root").write_bytes(b"fixture, not real histograms")
        (root / "plots/Waveform_Layer00.png").write_bytes(payload)
        (root / "plots/TOA_ADC_Layer00.png").write_bytes(b"other fixture pixels")

    def test_config_and_command_absolute_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = real.validate_config(self.config(root))
            command = real.command_for(config, root / "HGCROCStudy", root / "trial")
            self.assertEqual(command[command.index("-i") + 1], str(root / "data with spaces.root"))
            self.assertEqual(command[command.index("-o") + 1], str(root / "trial/analysis.root"))
            self.assertEqual(command[command.index("-F") + 1], "png")
            self.assertNotIn("-f", command)

    def test_config_rejects_unsafe_or_ambiguous_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self.config(root)
            changes = [lambda c: c["argv"].append("-f"),
                       lambda c: c["argv"].extend(["-i", "{input}"]),
                       lambda c: c["argv"].__setitem__(0, "/bin/sh"),
                       lambda c: c["argv"].__setitem__(c["argv"].index("-o") + 1, "/tmp/existing.root"),
                       lambda c: c["argv"].__setitem__(c["argv"].index("-O") + 1, "{output}/../../escape"),
                       lambda c: c["argv"].remove("-w"),
                       lambda c: c["argv"].__setitem__(c["argv"].index("-i") + 1, "{input.__class__}"),
                       lambda c: c["inputs"].__setitem__("input", "relative.root"),
                       lambda c: c["argv"].__setitem__(c["argv"].index("-L") + 1, "0")]
            for change in changes:
                config = copy.deepcopy(base)
                change(config)
                with self.subTest(config=config), self.assertRaises(RuntimeError):
                    real.validate_config(config)

    def test_safe_output_paths(self):
        self.assertEqual(str(real.safe_output_path(Path("/tmp/safe-name_123"))), "/tmp/safe-name_123")
        for path in ["/tmp/has space", "/tmp/a;echo", "/tmp/$(echo)", "/tmp/a\nb", "/tmp/café", "/tmp/test.root-data"]:
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                real.safe_output_path(Path(path))

    def test_missing_input_rejected(self):
        config = real.waveform_config(Path("/nonexistent/benchmark/input.root"), Path("/nonexistent/benchmark/runs"), None, 1000)
        with self.assertRaises(RuntimeError):
            real.validate_config(config)
        real.validate_config(config, check_files=False)

    def test_input_snapshot_detects_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(Path(directory))
            before = real.input_snapshot(config["inputs"], True)
            Path(config["inputs"]["input"]).write_bytes(b"modified")
            self.assertNotEqual(before, real.input_snapshot(config["inputs"], True))

    def test_hist_suffix_and_plot_set_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "analysis.root").write_bytes(b"wrong file")
            with self.assertRaises(RuntimeError):
                real.inspect_outputs(root, "png")
            self.outputs(root)
            result = real.inspect_outputs(root, "png")
            self.assertEqual(set(result["plot_sha256"]), {"Waveform_Layer00.png", "TOA_ADC_Layer00.png"})
            (root / "plots/Waveform_Layer00.png").unlink()
            with self.assertRaises(RuntimeError):
                real.inspect_outputs(root, "png")

    def test_summary_does_not_claim_root_correctness(self):
        base = dict(variant="base", elapsed_seconds=2, peak_rss_kib=2048, plot_sha256={"a.png": "same"})
        pr = dict(base, variant="pr90", elapsed_seconds=1, peak_rss_kib=1024)
        result = real.summarize([base, pr])
        self.assertEqual(result["stats"]["end_to_end_speedup_ratio"], 2)
        self.assertTrue(result["plot_bytes_equal"])
        self.assertFalse(result["root_histogram_semantics_checked"])
        pr["plot_sha256"] = {"a.png": "changed"}
        self.assertTrue(real.summarize([base, pr])["plot_files_equal"])
        self.assertFalse(real.summarize([base, pr])["plot_bytes_equal"])
        pr["plot_sha256"] = {"other.png": "same"}
        self.assertFalse(real.summarize([base, pr])["plot_files_equal"])

    def test_dry_run_no_dependencies_or_writes_and_default_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "never-created"
            output = io.StringIO()
            with contextlib.redirect_stdout(output), patch.object(real, "prerequisites", side_effect=AssertionError("must not run")):
                rc = real.main(["--input", "/not/here.root", "--runlist", "/not/runs.txt", "--out", str(out), "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse(out.exists())
            command = json.loads(output.getvalue())["example_command"]
            self.assertEqual(command[command.index("-L") + 1], "1000")
            self.assertNotIn("-L", real.waveform_config(Path("/a"), Path("/b"), None, None)["argv"])

    @unittest.skipUnless(sys.platform in {"linux", "darwin"}, "wait4 platform")
    def test_real_child_measurement_not_cumulative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with contextlib.redirect_stdout(io.StringIO()):
                high = real.measured_process([sys.executable, "-c", "a=bytearray(96*1024*1024); print(len(a))"], root, root / "high.log")
                low = real.measured_process([sys.executable, "-c", "print('small child')"], root, root / "low.log")
                failed = real.measured_process([sys.executable, "-c", "raise SystemExit(7)"], root, root / "failed.log")
            self.assertEqual(high["returncode"], 0)
            self.assertEqual(low["returncode"], 0)
            self.assertGreater(low["elapsed_seconds"], 0)
            self.assertGreater(high["peak_rss_kib"], low["peak_rss_kib"] + 50 * 1024)
            self.assertEqual(failed["returncode"], 7)
            self.assertEqual(low["library_search_paths"]["LD_LIBRARY_PATH"].split(":")[0], str(Path(sys.executable).resolve().parent))

    def test_check_only_and_dry_run_mutually_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            real.main(["--check-only", "--dry-run"])

    def test_mocked_build_orchestration_order_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(self.config(root)))
            out = root / "results"
            order = []
            def fake_build(source, build_dir, env, jobs, log):
                build_dir.mkdir()
                return build_dir / "HGCROCStudy"
            def fake_process(command, cwd, log):
                self.assertFalse((cwd / "analysis_Hists.root").exists())
                self.assertTrue(Path(command[command.index("-i") + 1]).is_absolute())
                order.append(cwd.name)
                self.outputs(cwd)
                log.write_text("mock execution")
                return dict(returncode=0, elapsed_seconds=1.0, peak_rss_kib=1024,
                            user_cpu_seconds=0.5, system_cpu_seconds=0.1)
            with contextlib.redirect_stdout(io.StringIO()), patch.object(real, "prerequisites", return_value={}), \
                    patch.object(real, "checkout"), patch.object(real, "verify_scope"), \
                    patch.object(real, "build_analysis", side_effect=fake_build), \
                    patch.object(real, "measured_process", side_effect=fake_process):
                args = ["--config", str(config_path), "--out", str(out), "--trials", "2"]
                self.assertEqual(real.main(args), 0)
                with self.assertRaises(RuntimeError):
                    real.main(args)
            self.assertEqual(order, ["trial-01-base", "trial-01-pr90", "trial-02-pr90", "trial-02-base"])
            summary = json.loads((out / "summary.json").read_text())
            self.assertTrue(summary["input_files_unchanged_on_disk"])
            self.assertTrue(summary["plot_bytes_equal"])
            self.assertFalse(summary["root_histogram_semantics_checked"])
            self.assertEqual(len(summary["trials"]), 4)


if __name__ == "__main__":
    unittest.main()
