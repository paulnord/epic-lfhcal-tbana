"""Synthetic byte-copy/archive checks; no real detector data or ROOT needed."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

import collect_hv_histograms as collector


class CollectorTests(unittest.TestCase):
    def fixture(self, temporary, runs=None):
        work = Path(temporary) / "campaign with spaces"
        output = Path(temporary) / "bundles"
        work.mkdir()
        output.mkdir()
        runs = sorted(collector.RUN_HV) if runs is None else runs
        original = {}
        for record in collector.required_inputs(work, runs):
            path = Path(record["source_absolute"])
            path.parent.mkdir(exist_ok=True)
            # Intentionally not valid ROOT. The collector must treat this as bytes.
            payload = (b"SYNTHETIC ONLY\x00\xff\n" + record["relative_path"].encode("ascii") + b"\n")
            path.write_bytes(payload)
            original[path] = payload
        forbidden = work / "final" / "calib_Final_194.root"
        forbidden.parent.mkdir()
        forbidden.write_bytes(b"EVENT ROOT MUST NEVER BE COPIED")
        original[forbidden] = forbidden.read_bytes()
        return work, output, original

    def assert_sources_unchanged(self, original):
        for path, payload in original.items():
            self.assertEqual(path.read_bytes(), payload, str(path))

    def test_default_complete_archive_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, parent, original = self.fixture(temporary)
            output, archive, checksum = collector.collect(work, parent)
            self.assert_sources_unchanged(original)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["file_count"], 27)
            self.assertEqual([item["run"] for item in manifest["runs"]], list(range(194, 203)))
            self.assertEqual(manifest["histogram_stage"], "refine2")
            self.assertTrue(manifest["hostname"])
            self.assertLessEqual(manifest["started_utc"], manifest["finished_utc"])
            self.assertTrue(manifest["started_utc"].endswith("+00:00"))
            self.assertEqual(manifest["source_work_absolute"], str(work.resolve()))
            by_run = {}
            with tarfile.open(str(archive), "r:gz") as bundle:
                expected = {item["relative_path"] for item in manifest["files"]}
                expected.update(["manifest.json", "collector/collect_hv_histograms.py"])
                self.assertEqual(set(bundle.getnames()), expected)
                self.assertEqual(len(bundle.getmembers()), 29)
                for item in manifest["files"]:
                    by_run.setdefault(item["run"], []).append(item)
                    self.assertEqual(item["hv_volts"], collector.RUN_HV[item["run"]])
                    source = Path(item["source_absolute"])
                    payload = original[source]
                    self.assertEqual(bundle.extractfile(item["relative_path"]).read(), payload)
                    self.assertEqual((output / item["relative_path"]).read_bytes(), payload)
                    self.assertEqual(item["size_bytes"], len(payload))
                    self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest())
                self.assertEqual(json.load(bundle.extractfile("manifest.json")), manifest)
                code = bundle.extractfile("collector/collect_hv_histograms.py").read()
                self.assertEqual(code, Path(collector.__file__).read_bytes())
                self.assertEqual(hashlib.sha256(code).hexdigest(), manifest["collector"]["sha256"])
            for items in by_run.values():
                self.assertEqual({(item["stage"], item["kind"]) for item in items},
                                 {("refine2", "histograms"), ("refine1", "seed_calibration"),
                                  ("refine2", "result_calibration")})
            self.assertEqual(checksum.read_text(), "{}  {}\n".format(
                hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name))
            self.assertFalse(Path(str(archive) + ".partial").exists())

    def test_missing_inputs_fail_before_any_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, parent, original = self.fixture(temporary)
            missing = [path for path in original if "_194_Hists" in path.name or "_202_calib" in path.name]
            for path in missing:
                path.unlink()
                del original[path]
            with self.assertRaises(ValueError) as caught:
                collector.collect(work, parent)
            for path in missing:
                self.assertIn(str(path), str(caught.exception))
            self.assertEqual(list(parent.iterdir()), [])
            self.assert_sources_unchanged(original)

    def test_repeated_collection_creates_new_bundle_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, parent, original = self.fixture(temporary, [194])
            first = collector.collect(work, parent, [194])
            saved = {path: path.read_bytes() for path in parent.rglob("*") if path.is_file()}
            second = collector.collect(work, parent, [194])
            self.assertTrue(set(first).isdisjoint(second))
            for path, payload in saved.items():
                self.assertEqual(path.read_bytes(), payload)
            self.assert_sources_unchanged(original)

    def test_empty_histogram_fails_before_any_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, parent, original = self.fixture(temporary, [194])
            histogram = next(path for path in original if path.name.endswith("_Hists.root"))
            histogram.write_bytes(b"")
            original[histogram] = b""
            with self.assertRaisesRegex(ValueError, "empty required inputs") as caught:
                collector.collect(work, parent, [194])
            self.assertIn(str(histogram), str(caught.exception))
            self.assertEqual(list(parent.iterdir()), [])
            self.assert_sources_unchanged(original)

    def test_source_change_is_detected_and_no_archive_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, parent, original = self.fixture(temporary, [194])
            real_copy = collector.copy_exclusive
            changed = [False]

            def mutate_source_after_copy(source, destination):
                real_copy(source, destination)
                if not changed[0]:
                    Path(source).write_bytes(b"SYNTHETIC CONCURRENT MODIFICATION")
                    changed[0] = True

            with mock.patch.object(collector, "copy_exclusive", side_effect=mutate_source_after_copy):
                with self.assertRaisesRegex(RuntimeError, "source changed"):
                    collector.collect(work, parent, [194])
            self.assertEqual(list(parent.glob("*.tgz")), [])
            failures = list(parent.glob("*/failure.json"))
            self.assertEqual(len(failures), 1)
            self.assertEqual(json.loads(failures[0].read_text())["status"], "failed")

    def test_explicit_subset_cli_and_duplicate_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, parent, original = self.fixture(temporary, [194, 202])
            result = subprocess.run([sys.executable, collector.__file__, "--work", str(work),
                                     "--out-parent", str(parent), "--runs", "202", "194"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifests = list(parent.glob("*/manifest.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text())
            self.assertEqual(manifest["file_count"], 6)
            self.assertEqual([item["run"] for item in manifest["runs"]], [194, 202])
            before = set(parent.iterdir())
            for runs in ([194, 194], [193], []):
                with self.assertRaises(ValueError):
                    collector.collect(work, parent, runs)
            self.assertEqual(set(parent.iterdir()), before)
            self.assert_sources_unchanged(original)


if __name__ == "__main__":
    unittest.main()
