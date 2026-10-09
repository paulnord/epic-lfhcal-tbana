"""Exercise R5 preparation against yall-run's real campaign-start output guard."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from yall_run.campaign import create_campaign, prepare_campaign_start
from yall_run.model import load_spec

REPO = Path(__file__).parent
RECIPE = Path("examples/yall/ps-replot-r5")
spec = importlib.util.spec_from_file_location("prepare_r5", REPO / RECIPE / "prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class ReplotPreparation(unittest.TestCase):
    def test_fresh_setup_and_old_empty_directory_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, reference, work = (base / n for n in ("source", "reference", "work"))
            recipe = source / RECIPE
            recipe.mkdir(parents=True)
            shutil.copy(REPO / RECIPE / "Yallfile", recipe / "Yallfile")
            support = source / "examples/yall/calibration-2026"
            support.mkdir()
            for name in ("run-in-eic-shell.sh", "in-calibration-build.sh"):
                shutil.copy2(REPO / "examples/yall/calibration-2026" / name, support / name)
            build = source / "NewStructure/build"
            build.mkdir(parents=True)
            for name in ("TileSpectra.cc", "FitCurveDrawing.h"):
                shutil.copy(REPO / "NewStructure" / name, build.parent / name)
            (build / "DataPrep").write_text("#!/bin/sh\nexit 0\n")
            (build / "DataPrep").chmod(0o755)
            (build / "libLFHCAL.so").write_text("fixture\n")
            cfg = source / "configs/TB2026"
            cfg.mkdir(parents=True)
            (cfg / "DataTakingDB_TBPST10_202604_HGCROC.csv").write_text("fixture\n")
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
            env = dict(PS_REFERENCE=str(reference), PLOT_WORK=str(work),
                       PLOT_SOURCE=str(source), EIC_SHELL="/bin/true")
            with patch.dict(os.environ, env):
                workflow = load_spec(recipe / "Yallfile")
                for task in workflow.tasks:
                    for item in task.inputs:
                        path = Path(item.path)
                        if str(path).startswith(str(reference) + "/"):
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_text("fixture\n")
                prepare.main()
                prepare.main()  # Repeating preparation must not create outputs.
                workflow = load_spec(work / "Yallfile")
                self.assertEqual(len(workflow.tasks), 17)
                for task in workflow.tasks:
                    for output in task.outputs:
                        path = Path(output.path)
                        self.assertTrue(path.parent.is_dir())
                        self.assertFalse(path.exists(), str(path))
                campaign = create_campaign(workflow, work / "campaigns", backend="local")
                plot = Path(next(o.path for o in workflow.tasks[0].outputs if o.role == "plots"))
                plot.mkdir()  # Reproduce the original preparation bug.
                with self.assertRaisesRegex(ValueError, "declared outputs already exist"):
                    prepare_campaign_start(campaign)
                plot.rmdir()  # Same nonrecursive recovery recommended to the user.
                prepare_campaign_start(campaign)  # No overwrite switch is needed.


if __name__ == "__main__":
    unittest.main()
