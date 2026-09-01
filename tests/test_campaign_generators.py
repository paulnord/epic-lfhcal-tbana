#!/usr/bin/env python3

import importlib.machinery
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
TOOLS = REPOSITORY / "tools"
RUNNER = TOOLS / "lfhcal-run"
PARAMSCAN = TOOLS / "make-tb2026-paramscan-campaign"
PARAMSCAN_COMPAT = TOOLS / "make-tb2026-paramscan-dag"
CONVERSION = TOOLS / "make-tb2026-conversion-campaign"
ANALYSIS = TOOLS / "make-tb2026-analysis-campaign"


def load_runner():
    loader = importlib.machinery.SourceFileLoader("campaign_test_lfhcal_run", str(RUNNER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


class CampaignGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load_runner()

    def generate(self, tool: pathlib.Path, arguments: list[str], manifest: pathlib.Path):
        result = subprocess.run(
            [sys.executable, str(tool), *arguments, "--manifest", str(manifest)],
            cwd=manifest.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.runner.parse_manifest(manifest, None)

    def test_parameter_scan_public_and_compatibility_names_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            arguments = [
                "--repository",
                str(REPOSITORY),
                "--raw-dir",
                str(work / "raw"),
                "--output-dir",
                str(work / "products"),
            ]
            public = work / "public.txt"
            legacy = work / "legacy.txt"
            public_jobs = self.generate(PARAMSCAN, arguments, public)
            legacy_jobs = self.generate(PARAMSCAN_COMPAT, arguments, legacy)

        self.assertEqual(len(public_jobs), 12)
        self.assertEqual(
            [(job.name, job.parents, job.retries) for job in public_jobs],
            [(job.name, job.parents, job.retries) for job in legacy_jobs],
        )

    def test_conversion_campaign_expands_runs_into_independent_jobs(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            jobs = self.generate(
                CONVERSION,
                [
                    "--repository",
                    str(REPOSITORY),
                    "--raw-dir",
                    str(work / "raw"),
                    "--output-dir",
                    str(work / "converted"),
                    "137",
                    "138-139",
                ],
                work / "conversion.txt",
            )

        self.assertEqual([job.name for job in jobs], ["prepare", "convert-137", "convert-138", "convert-139"])
        self.assertTrue(all(job.parents == ["prepare"] for job in jobs[1:]))
        self.assertTrue(all(job.retries == 1 for job in jobs))
        self.assertTrue(jobs[-1].command[jobs[-1].command.index("-c") + 1].endswith("Run139.h2g"))

    def test_analysis_campaign_builds_calibration_and_parallel_data_branches(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            bad_channels = work / "bad-channels.txt"
            toa_offsets = work / "toa-offsets.csv"
            jobs = self.generate(
                ANALYSIS,
                [
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
                    str(bad_channels),
                    "--toa-offsets",
                    str(toa_offsets),
                    "153",
                    "159",
                    "165",
                    "178",
                ],
                work / "analysis.txt",
            )

        self.assertEqual(len(jobs), 36)
        by_name = {job.name: job for job in jobs}
        self.assertEqual(by_name["convert-137"].parents, ["prepare"])
        self.assertEqual(
            by_name["merge-muons"].parents,
            [f"convert-{run}" for run in range(138, 150)],
        )
        self.assertEqual(by_name["pedestal"].parents, ["convert-137"])
        self.assertEqual(
            by_name["transfer-calibration"].parents,
            ["pedestal", "merge-muons"],
        )
        self.assertEqual(by_name["muon-calibration"].parents, ["transfer-calibration"])
        self.assertEqual(by_name["select-mip"].parents, ["muon-calibration"])
        self.assertEqual(by_name["refine-1"].parents, ["select-mip"])
        self.assertEqual(by_name["refine-4"].parents, ["refine-3"])
        self.assertEqual(by_name["strip-calibration"].parents, ["refine-4"])
        self.assertEqual(by_name["convert-153"].parents, ["prepare"])
        self.assertEqual(
            by_name["apply-calibration-153"].parents,
            ["strip-calibration", "convert-153"],
        )
        self.assertEqual(by_name["waveform-153"].parents, ["apply-calibration-153"])
        calibration = str(work / "analysis" / "calib_FullSetC_1.root")
        apply = by_name["apply-calibration-153"]
        self.assertEqual(apply.command[apply.command.index("-C") + 1], calibration)
        self.assertEqual(
            next(item.path for item in apply.inputs if item.role == "final_calibration"),
            calibration,
        )
        self.assertEqual(
            next(
                item.path
                for item in by_name["strip-calibration"].outputs
                if item.role == "final_calibration"
            ),
            calibration,
        )
        self.assertTrue(by_name["waveform-153"].command[0].endswith("/HGCROCStudy"))
        self.assertNotIn("-l", by_name["waveform-153"].command)

    def test_analysis_campaign_rejects_descending_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ANALYSIS),
                    "--raw-dir",
                    str(work),
                    "--output-dir",
                    str(work / "out"),
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
                    str(work / "campaign.txt"),
                    "149-138",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("run range must be ascending", result.stderr)


if __name__ == "__main__":
    unittest.main()
