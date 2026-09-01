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
CONTAINER_WRAPPER = REPOSITORY / "tools" / "run-in-eic-container.sh"
PARAMSCAN_DAG_GENERATOR = REPOSITORY / "tools" / "make-tb2026-paramscan-dag"


def load_tool():
    loader = importlib.machinery.SourceFileLoader("lfhcal_run", str(TOOL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


class LFHCalRunTests(unittest.TestCase):
    def test_backend_option_is_not_public(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--backend",
                    "condor",
                    "--dry-run",
                    "--",
                    sys.executable,
                    "-c",
                    "print('not submitted')",
                ],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("unrecognized arguments: --backend", result.stderr)
            self.assertFalse((work / "lfhcal-runs").exists())

    def test_condor_rejects_local_jobs_option(self):
        for option in ("-j", "--jobs"):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as temporary:
                work = pathlib.Path(temporary)
                result = subprocess.run(
                    [
                        sys.executable,
                        str(TOOL),
                        "--condor",
                        option,
                        "4",
                        "--dry-run",
                        "--",
                        sys.executable,
                        "-c",
                        "print('not submitted')",
                    ],
                    cwd=work,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(
                    "-j/--jobs applies only to local execution",
                    result.stderr,
                )
                self.assertFalse((work / "lfhcal-runs").exists())

    def test_tb2026_paramscan_generator_builds_full_imp3r_chain(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            raw = work / "raw"
            output = work / "products"
            manifest = work / "full-chain.txt"
            result = subprocess.run(
                [
                    sys.executable,
                    str(PARAMSCAN_DAG_GENERATOR),
                    "--repository",
                    str(REPOSITORY),
                    "--raw-dir",
                    str(raw),
                    "--output-dir",
                    str(output),
                    "--manifest",
                    str(manifest),
                ],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            jobs = tool.parse_manifest(manifest, None)

        self.assertEqual(len(jobs), 12)
        by_name = {job.name: job for job in jobs}
        self.assertEqual(
            by_name["transfer-calibration-298"].parents,
            ["pedestal-296", "convert-muon-298"],
        )
        self.assertEqual(by_name["waveform-298"].parents, ["apply-calibration-298"])
        self.assertTrue(all(job.retries == 1 for job in jobs))
        apply_job = by_name["apply-calibration-298"]
        calibration_argument = apply_job.command[apply_job.command.index("-C") + 1]
        self.assertTrue(calibration_argument.endswith("rawHGCROC_wPedwMuon_wBC_Imp3R_298.root"))
        self.assertEqual(
            next(item.path for item in apply_job.inputs if item.role == "final_calibration"),
            calibration_argument,
        )
        waveform_job = by_name["waveform-298"]
        self.assertTrue(waveform_job.command[0].endswith("/NewStructure/build/HGCROCStudy"))
        self.assertIn("activeCellsHGCROCParameterScan.txt", waveform_job.command[-1])

    def test_campaign_notes_are_recorded_separately_from_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--dry-run",
                    "--note",
                    "First note",
                    "--note",
                    "Second note",
                    "--",
                    sys.executable,
                    "-c",
                    "print('notes')",
                ],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            campaign_path = next((work / "lfhcal-runs").glob("*/campaign.json"))
            campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
            self.assertEqual(campaign["notes"], ["First note", "Second note"])
            self.assertEqual(campaign["jobs"][0]["inputs"], [])

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
                    self.assertEqual(
                        tool.logical_invocation_path(
                            str(physical / "tools" / "lfhcal-run"), logical
                        ),
                        logical / "tools" / "lfhcal-run",
                    )
            finally:
                os.chdir(previous)

    def test_cvmfs_container_digest_is_recovered_from_resolved_path(self):
        tool = load_tool()
        digest = "50" + "7" * 62
        path = f"/cvmfs/example/.images/sha256:{digest[:2]}/{digest[2:]}"
        self.assertEqual(
            tool.digest_from_cvmfs_image_path(path),
            f"sha256:{digest}",
        )

    def test_eic_container_wrapper_preserves_payload_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            image = work / "image"
            image.mkdir()
            binary_dir = work / "bin"
            binary_dir.mkdir()
            runtime = binary_dir / "apptainer"
            runtime.write_text(
                "#!/bin/sh\n"
                "test \"$1\" = exec || exit 90\n"
                "test \"$APPTAINER_BINDPATH\" = /already-bound,/custom/data || exit 92\n"
                "shift\n"
                "test \"$1\" = \"$LFHCAL_CONTAINER_IMAGE\" || exit 91\n"
                "shift\n"
                "exec \"$@\"\n",
                encoding="utf-8",
            )
            runtime.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{binary_dir}{os.pathsep}{environment['PATH']}"
            environment["LFHCAL_CONTAINER_IMAGE"] = str(image)
            environment["LFHCAL_CONTAINER_BINDPATH"] = "/custom/data"
            environment["APPTAINER_BINDPATH"] = "/already-bound"
            result = subprocess.run(
                [
                    str(CONTAINER_WRAPPER),
                    sys.executable,
                    "-c",
                    "import sys; print(sys.argv[1])",
                    "argument with spaces",
                ],
                cwd=work,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "argument with spaces")

    def test_execution_record_captures_active_container(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            digest = "ab" + "c" * 62
            resolved_image = work / ".images" / "sha256:ab" / ("c" * 62)
            resolved_image.mkdir(parents=True)
            image = work / "eic_xl-nightly"
            image.symlink_to(resolved_image, target_is_directory=True)
            environment = os.environ.copy()
            environment["APPTAINER_CONTAINER"] = str(image)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--cwd",
                    str(work),
                    "--",
                    sys.executable,
                    "-c",
                    "print('inside container')",
                ],
                cwd=work,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            latest = next((work / "lfhcal-runs").glob("*/jobs/*/latest.json"))
            record = json.loads(latest.read_text(encoding="utf-8"))
            self.assertEqual(record["container"]["content_digest"], f"sha256:{digest}")
            self.assertEqual(record["host"]["python_executable"], sys.executable)

    def test_manifest_supports_arbitrary_commands_and_metadata(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "jobs.txt"
            path.write_text(
                "# comment\n"
                "JOB summary -- python3 custom.py --mode bananas\n"
                "JOB calibration --input pedestal=ped.root "
                "--input muon=mu.root --output calibrated=out.root -- "
                "./DataPrep -i mu.root -P ped.root -o out.root\n",
                encoding="utf-8",
            )
            jobs = tool.parse_manifest(path, None)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].name, "summary")
        self.assertEqual(jobs[0].command, ["python3", "custom.py", "--mode", "bananas"])
        self.assertEqual(jobs[1].name, "calibration")
        self.assertEqual([item.role for item in jobs[1].inputs], ["pedestal", "muon"])
        self.assertEqual(jobs[1].outputs[0].role, "calibrated")

    def test_manifest_requires_job_records(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "jobs.txt"
            path.write_text("python3 custom.py --mode bananas\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "job lines must use JOB NAME"):
                tool.parse_manifest(path, None)

    def test_manifest_rejects_duplicate_job_names_without_dependencies(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "jobs.txt"
            path.write_text(
                "JOB repeated -- python3 first.py\n"
                "JOB repeated -- python3 second.py\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate DAG job name"):
                tool.parse_manifest(path, None)

    def test_manifest_supports_dagman_style_dependencies_and_retries(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "campaign.txt"
            path.write_text(
                "JOB pedestal -- python3 pedestal.py\n"
                "JOB muon -- python3 muon.py\n"
                "JOB calibration --input pedestal=ped.root --input muon=mu.root "
                "--output calibrated=out.root -- python3 calibrate.py\n"
                "PARENT pedestal muon CHILD calibration\n"
                "RETRY calibration 2\n",
                encoding="utf-8",
            )
            jobs = tool.parse_manifest(path, None)
        self.assertEqual([job.name for job in jobs], ["pedestal", "muon", "calibration"])
        self.assertEqual(jobs[2].parents, ["pedestal", "muon"])
        self.assertEqual(jobs[2].retries, 2)

    def test_manifest_rejects_dependency_cycles(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "campaign.txt"
            path.write_text(
                "JOB first -- python3 first.py\n"
                "JOB second -- python3 second.py\n"
                "PARENT first CHILD second\n"
                "PARENT second CHILD first\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "dependency cycle"):
                tool.parse_manifest(path, None)

    def test_local_parallel_run_records_attempts(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            manifest = work / "jobs.txt"
            manifest.write_text(
                "JOB first --output result=one.txt -- "
                "python3 -c 'from pathlib import Path; Path(\"one.txt\").write_text(\"1\")'\n"
                "JOB second --output result=two.txt -- "
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
            campaign_paths = list((work / "lfhcal-runs").glob("*/campaign.json"))
            self.assertEqual(len(campaign_paths), 1)
            campaign = json.loads(campaign_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(campaign["status"], "completed")
            latest = list(campaign_paths[0].parent.glob("jobs/*/latest.json"))
            self.assertEqual(len(latest), 2)
            records = [json.loads(path.read_text(encoding="utf-8")) for path in latest]
            self.assertTrue(all(record["exit_code"] == 0 for record in records))
            self.assertTrue(all(record["outputs"][0]["exists"] for record in records))

    def test_local_dag_retries_parent_before_running_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            retry_script = work / "retry_once.py"
            retry_script.write_text(
                "from pathlib import Path\n"
                "marker = Path('attempt-count')\n"
                "count = int(marker.read_text()) + 1 if marker.exists() else 1\n"
                "marker.write_text(str(count))\n"
                "raise SystemExit(0 if count >= 2 else 9)\n",
                encoding="utf-8",
            )
            child_script = work / "child.py"
            child_script.write_text(
                "from pathlib import Path\n"
                "assert Path('attempt-count').read_text() == '2'\n"
                "Path('done.txt').write_text('done')\n",
                encoding="utf-8",
            )
            manifest = work / "campaign.txt"
            manifest.write_text(
                f"JOB first -- {sys.executable} {retry_script}\n"
                f"JOB second --output result=done.txt -- {sys.executable} {child_script}\n"
                "PARENT first CHILD second\n"
                "RETRY first 1\n",
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
            campaign_path = next((work / "lfhcal-runs").glob("*/campaign.json"))
            campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
            self.assertEqual(campaign["status"], "completed")
            self.assertEqual(campaign["dag"]["retries"], {"first": 1})
            self.assertEqual([item["status"] for item in campaign["job_statuses"]], [
                "completed",
                "completed",
            ])
            first_attempts = list(
                campaign_path.parent.glob("jobs/0000-first/attempts/attempt-*")
            )
            self.assertEqual(len(first_attempts), 2)
            self.assertEqual((work / "done.txt").read_text(encoding="utf-8"), "done")

    def test_local_dag_blocks_child_after_parent_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            fail_script = work / "fail.py"
            fail_script.write_text("raise SystemExit(3)\n", encoding="utf-8")
            child_script = work / "child.py"
            child_script.write_text(
                "from pathlib import Path\nPath('should-not-exist').touch()\n",
                encoding="utf-8",
            )
            manifest = work / "campaign.txt"
            manifest.write_text(
                f"JOB first -- {sys.executable} {fail_script}\n"
                f"JOB second -- {sys.executable} {child_script}\n"
                "PARENT first CHILD second\n",
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
            self.assertEqual(result.returncode, 3, result.stderr)
            campaign_path = next((work / "lfhcal-runs").glob("*/campaign.json"))
            campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
            self.assertEqual(campaign["failed_jobs"], 1)
            self.assertEqual(campaign["blocked_jobs"], 1)
            self.assertFalse((work / "should-not-exist").exists())

    def test_condor_dag_dry_run_creates_dagman_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            manifest = work / "campaign.txt"
            manifest.write_text(
                "JOB parent -- python3 first.py\n"
                "JOB child -- python3 second.py\n"
                "PARENT parent CHILD child\n"
                "RETRY parent 2\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(TOOL), "--condor", "--dry-run", str(manifest)],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            campaign_path = next((work / "lfhcal-runs").glob("*/campaign.json"))
            campaign_dir = campaign_path.parent
            submit = (campaign_dir / "condor.sub").read_text(encoding="utf-8")
            dag = (campaign_dir / "campaign.dag").read_text(encoding="utf-8")
            self.assertIn("arguments = $(lfhcal_job_index)", submit)
            self.assertIn("LFHCAL_CONDOR_DAG_NODE=$(lfhcal_node)", submit)
            self.assertIn("output = " + str(campaign_dir / "condor") + "/$(lfhcal_node).out", submit)
            self.assertIn("queue 1", submit)
            self.assertIn(f"JOB lfhcal_0000_parent {campaign_dir / 'condor.sub'}", dag)
            self.assertIn(
                'VARS lfhcal_0001_child lfhcal_job_index="1" lfhcal_node="child"',
                dag,
            )
            self.assertIn("RETRY lfhcal_0000_parent 2", dag)
            self.assertIn(
                "PARENT lfhcal_0000_parent CHILD lfhcal_0001_child",
                dag,
            )
            finalize_submit = campaign_dir / "condor_finalize.sub"
            self.assertIn(
                f"FINAL lfhcal_finalize {finalize_submit}",
                dag,
            )
            self.assertIn(
                "universe = local",
                finalize_submit.read_text(encoding="utf-8"),
            )
            self.assertIn(
                " _finalize --campaign ",
                (campaign_dir / "condor_finalize.sh").read_text(encoding="utf-8"),
            )
            campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
            self.assertEqual(campaign["condor_dag_file"], str(campaign_dir / "campaign.dag"))
            self.assertEqual(
                campaign["condor_finalize_submit_file"], str(finalize_submit)
            )

    def test_independent_condor_jobs_use_condor_submit_dag(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            manifest = work / "campaign.txt"
            manifest.write_text(
                "JOB first -- python3 first.py\n"
                "JOB second -- python3 second.py\n",
                encoding="utf-8",
            )
            binary_dir = work / "bin"
            binary_dir.mkdir()
            argument_log = work / "submit-arguments.txt"
            submit_dag = binary_dir / "condor_submit_dag"
            submit_dag.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$LFHCAL_TEST_ARGUMENT_LOG\"\n",
                encoding="utf-8",
            )
            submit_dag.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{binary_dir}{os.pathsep}{environment['PATH']}"
            environment["LFHCAL_TEST_ARGUMENT_LOG"] = str(argument_log)
            result = subprocess.run(
                [sys.executable, str(TOOL), "--condor", str(manifest)],
                cwd=work,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            campaign_path = next((work / "lfhcal-runs").glob("*/campaign.json"))
            campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
            dag_path = campaign_path.parent / "campaign.dag"
            self.assertEqual(argument_log.read_text(encoding="utf-8").strip(), str(dag_path))
            dag = dag_path.read_text(encoding="utf-8")
            self.assertIn("JOB lfhcal_0000_first", dag)
            self.assertIn("JOB lfhcal_0001_second", dag)
            self.assertNotIn("PARENT", dag)
            self.assertEqual(
                campaign["condor_submit_command"],
                ["condor_submit_dag", str(dag_path)],
            )

    def test_single_condor_command_creates_one_node_dag(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--condor",
                    "--dry-run",
                    "--",
                    "python3",
                    "-c",
                    "print(42)",
                ],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            dag_path = next((work / "lfhcal-runs").glob("*/campaign.dag"))
            dag = dag_path.read_text(encoding="utf-8")
            self.assertIn("JOB lfhcal_0000_python3", dag)
            self.assertIn('lfhcal_job_index="0" lfhcal_node="0000-python3"', dag)

    def test_condor_dry_run_creates_submit_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            manifest = work / "jobs.txt"
            manifest.write_text("JOB answer -- python3 -c 'print(42)'\n", encoding="utf-8")
            wrapper = work / "container-wrapper.sh"
            wrapper.write_text("#!/bin/sh\nexec \"$@\"\n", encoding="utf-8")
            wrapper.chmod(0o755)
            eic_shell = work / "eic-shell"
            eic_shell.write_text("#!/bin/sh\necho interactive\n", encoding="utf-8")
            eic_shell.chmod(0o755)
            digest = "50" + "7" * 62
            resolved_image = work / ".images" / "sha256:50" / ("7" * 62)
            resolved_image.mkdir(parents=True)
            image = work / "eic_xl-nightly"
            image.symlink_to(resolved_image, target_is_directory=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--condor",
                    "--dry-run",
                    "--condor-wrapper",
                    str(wrapper),
                    "--environment-file",
                    str(eic_shell),
                    "--container-image",
                    str(image),
                    str(manifest),
                ],
                cwd=work,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            submit_paths = list((work / "lfhcal-runs").glob("*/condor.sub"))
            self.assertEqual(len(submit_paths), 1)
            submit = submit_paths[0].read_text(encoding="utf-8")
            campaign_dir = submit_paths[0].parent
            campaign = json.loads((campaign_dir / "campaign.json").read_text(encoding="utf-8"))
            worker = campaign_dir / "condor_worker.sh"
            archived_wrapper = campaign_dir / "environment" / "condor-wrapper.sh"
            self.assertNotIn("max_parallel", campaign)
            self.assertIn("LFHCAL_CONDOR_JOB_ID=$(ClusterId).$(ProcId)", submit)
            self.assertIn(f"LFHCAL_CONTAINER_IMAGE={resolved_image}", submit)
            self.assertIn(f"executable = {archived_wrapper}", submit)
            self.assertIn(f'arguments = "{worker} $(lfhcal_job_index)"', submit)
            self.assertIn("LFHCAL_CONDOR_DAG_NODE=$(lfhcal_node)", submit)
            self.assertIn(
                "output = " + str(campaign_dir / "condor") + "/$(lfhcal_node).out",
                submit,
            )
            self.assertIn("queue 1", submit)
            dag = (campaign_dir / "campaign.dag").read_text(encoding="utf-8")
            self.assertIn(f"JOB lfhcal_0000_answer {campaign_dir / 'condor.sub'}", dag)
            self.assertIn(
                'VARS lfhcal_0000_answer lfhcal_job_index="0" lfhcal_node="answer"',
                dag,
            )
            self.assertTrue(archived_wrapper.is_file())
            self.assertIn("exec python3 ", worker.read_text(encoding="utf-8"))

            campaign = json.loads((campaign_dir / "campaign.json").read_text(encoding="utf-8"))
            environment = campaign["execution_environment"]
            self.assertEqual(
                environment["container_image"]["content_digest"],
                f"sha256:{digest}",
            )
            self.assertEqual(
                pathlib.Path(environment["container_image"]["resolved_path"]),
                resolved_image,
            )
            self.assertEqual(len(environment["archived_files"]), 1)
            archived_eic_shell = pathlib.Path(
                environment["archived_files"][0]["archived_path"]
            )
            self.assertEqual(
                archived_eic_shell.read_text(encoding="utf-8"),
                eic_shell.read_text(encoding="utf-8"),
            )
            self.assertTrue(environment["condor_wrapper"]["sha256"].startswith("sha256:"))

            worker_result = subprocess.run(
                [str(archived_wrapper), str(worker), "0"],
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

    def test_status_reconciles_completed_condor_campaign(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            campaign_dir = pathlib.Path(temporary) / "campaign-test"
            campaign_path = campaign_dir / "campaign.json"
            jobs = [
                tool.JobSpec(command=["python3", "first.py"], inputs=[], outputs=[], name="first"),
                tool.JobSpec(command=["python3", "second.py"], inputs=[], outputs=[], name="second"),
            ]
            tool.atomic_json(
                campaign_path,
                {
                    "schema": tool.SCHEMA,
                    "kind": "campaign",
                    "campaign_id": "campaign-test",
                    "backend": "condor",
                    "status": "submitted",
                    "jobs": [job.to_dict() for job in jobs],
                },
            )
            for index, job in enumerate(jobs):
                job_dir = campaign_dir / "jobs" / tool.job_label(index, job)
                (job_dir / "attempts" / f"attempt-{index}").mkdir(parents=True)
                tool.atomic_json(job_dir / "latest.json", {"exit_code": 0})

            result = subprocess.run(
                [sys.executable, str(TOOL), "status", str(campaign_dir)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("campaign-test: completed", result.stdout)
            campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
            self.assertEqual(campaign["status"], "completed")
            self.assertEqual(campaign["completed_jobs"], 2)
            self.assertEqual(campaign["failed_jobs"], 0)
            self.assertEqual(
                [item["status"] for item in campaign["job_statuses"]],
                ["completed", "completed"],
            )

    def test_finalizer_records_failed_blocked_and_not_run_jobs(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            campaign_dir = pathlib.Path(temporary) / "campaign-test"
            campaign_path = campaign_dir / "campaign.json"
            jobs = [
                tool.JobSpec(command=["false"], inputs=[], outputs=[], name="parent"),
                tool.JobSpec(
                    command=["echo", "child"],
                    inputs=[],
                    outputs=[],
                    name="child",
                    parents=["parent"],
                ),
                tool.JobSpec(command=["echo", "independent"], inputs=[], outputs=[], name="independent"),
            ]
            tool.atomic_json(
                campaign_path,
                {
                    "schema": tool.SCHEMA,
                    "kind": "campaign",
                    "campaign_id": "campaign-test",
                    "backend": "condor",
                    "status": "submitted",
                    "jobs": [job.to_dict() for job in jobs],
                },
            )
            failed_dir = campaign_dir / "jobs" / tool.job_label(0, jobs[0])
            (failed_dir / "attempts" / "attempt-0").mkdir(parents=True)
            tool.atomic_json(failed_dir / "latest.json", {"exit_code": 9})

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "_finalize",
                    "--campaign",
                    str(campaign_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
            self.assertEqual(campaign["status"], "failed")
            self.assertEqual(campaign["failed_jobs"], 1)
            self.assertEqual(campaign["blocked_jobs"], 1)
            self.assertEqual(campaign["not_run_jobs"], 1)
            self.assertEqual(
                [item["status"] for item in campaign["job_statuses"]],
                ["failed", "blocked", "not_run"],
            )
            self.assertIn("ended_at", campaign)

    def test_status_recognizes_an_active_retry_attempt(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            campaign_dir = pathlib.Path(temporary) / "campaign-test"
            campaign_path = campaign_dir / "campaign.json"
            job = tool.JobSpec(
                command=["false"],
                inputs=[],
                outputs=[],
                name="retrying",
                retries=1,
            )
            tool.atomic_json(
                campaign_path,
                {
                    "schema": tool.SCHEMA,
                    "kind": "campaign",
                    "campaign_id": "campaign-test",
                    "backend": "condor",
                    "status": "submitted",
                    "jobs": [job.to_dict()],
                },
            )
            attempts_dir = campaign_dir / "jobs" / tool.job_label(0, job) / "attempts"
            first = attempts_dir / "attempt-0"
            second = attempts_dir / "attempt-1"
            first.mkdir(parents=True)
            second.mkdir()
            tool.atomic_json(first / "provenance.json", {"exit_code": 9})
            tool.atomic_json(second / "provenance.json", {"started_at": "now"})
            tool.atomic_json(attempts_dir.parent / "latest.json", {"exit_code": 9})

            campaign = tool.reconcile_campaign(campaign_path, final=False)
            self.assertEqual(campaign["status"], "running")
            self.assertEqual(campaign["running_jobs"], 1)
            self.assertEqual(campaign["job_statuses"][0]["active_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
