#!/usr/bin/env python3

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPOSITORY / "tools" / "lfhcal-run"


def load_tool():
    loader = importlib.machinery.SourceFileLoader("lfhcal_run", str(TOOL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


class LFHCalRunTests(unittest.TestCase):
    def test_named_and_unnamed_file_refs(self):
        tool = load_tool()
        named = tool.parse_file_ref("pedestal=/data/ped.root")
        unnamed = tool.parse_file_ref("relative.root")
        self.assertEqual((named.role, named.path), ("pedestal", "/data/ped.root"))
        self.assertEqual((unnamed.role, unnamed.path), (None, "relative.root"))

    def test_logical_paths_are_not_resolved_to_physical_mounts(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            physical = root / "direct"
            physical.mkdir()
            logical = root / "star"
            logical.symlink_to(physical, target_is_directory=True)

            self.assertEqual(
                tool.normalized_path("results/out.root", logical),
                logical / "results" / "out.root",
            )

            previous = pathlib.Path.cwd()
            try:
                os.chdir(physical)
                with mock.patch.dict(os.environ, {"PWD": str(logical)}):
                    self.assertEqual(tool.logical_cwd(), logical)
            finally:
                os.chdir(previous)

    def test_manifest_supports_arbitrary_commands_and_metadata(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "jobs.txt"
            path.write_text(
                "# comment\n"
                "python3 custom.py --mode bananas\n"
                "--name calibration --input pedestal=ped.root "
                "--input muon=mu.root --output calibrated=out.root -- "
                "./DataPrep -i mu.root -P ped.root -o out.root\n",
                encoding="utf-8",
            )
            jobs = tool.parse_manifest(path, None)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].command, ["python3", "custom.py", "--mode", "bananas"])
        self.assertEqual(jobs[1].name, "calibration")
        self.assertEqual([item.role for item in jobs[1].inputs], ["pedestal", "muon"])
        self.assertEqual(jobs[1].outputs[0].role, "calibrated")

    def test_local_parallel_run_records_attempts(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            manifest = work / "jobs.txt"
            manifest.write_text(
                "--name first --output result=one.txt -- "
                "python3 -c 'from pathlib import Path; Path(\"one.txt\").write_text(\"1\")'\n"
                "--name second --output result=two.txt -- "
                "python3 -c 'from pathlib import Path; Path(\"two.txt\").write_text(\"2\")'\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(TOOL), "-j", "2", "--cwd", str(work), str(manifest)],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            campaign_paths = list((work / ".lfhcal" / "runs").glob("*/campaign.json"))
            self.assertEqual(len(campaign_paths), 1)
            campaign = json.loads(campaign_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(campaign["status"], "completed")
            latest = list(campaign_paths[0].parent.glob("jobs/*/latest.json"))
            self.assertEqual(len(latest), 2)
            records = [json.loads(path.read_text(encoding="utf-8")) for path in latest]
            self.assertTrue(all(record["exit_code"] == 0 for record in records))
            self.assertTrue(all(record["outputs"][0]["exists"] for record in records))

    def test_condor_dry_run_creates_submit_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            manifest = work / "jobs.txt"
            manifest.write_text("python3 -c 'print(42)'\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOL), "--condor", "--dry-run", str(manifest)],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            submit_paths = list((work / ".lfhcal" / "runs").glob("*/condor.sub"))
            self.assertEqual(len(submit_paths), 1)
            submit = submit_paths[0].read_text(encoding="utf-8")
            self.assertIn("LFHCAL_CONDOR_JOB_ID=$(ClusterId).$(ProcId)", submit)
            self.assertIn("queue 1", submit)

            worker = submit_paths[0].parent / "condor_worker.sh"
            worker_result = subprocess.run(
                [str(worker), "0"],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(worker_result.returncode, 0, worker_result.stderr)
            latest = list(submit_paths[0].parent.glob("jobs/*/latest.json"))
            self.assertEqual(len(latest), 1)
            record = json.loads(latest[0].read_text(encoding="utf-8"))
            self.assertEqual(record["command"]["argv"][:2], ["python3", "-c"])


if __name__ == "__main__":
    unittest.main()
