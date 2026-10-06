"""Check Legacy comparison wiring with yall-run's actual parser; no ROOT needed."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from yall_run.model import load_spec

RECIPES = Path(__file__).parent / 'examples/yall'

class LegacyRecipes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root/'adaptive'
        self.work = self.root/'legacy'
        self.source = self.root/'source'
        self.env = {'PS_REFERENCE': str(self.reference), 'PS_LEGACY_WORK': str(self.work),
                    'PS_LEGACY_SOURCE': str(self.source), 'EIC_SHELL': '/bin/true'}

    def parse(self, path):
        with patch.dict(os.environ, self.env):
            return load_spec(path)

    def test_all_graphs_use_private_build_and_legacy_constants(self):
        paths = sorted(RECIPES.glob('ps-*/Yallfile.legacy'))
        self.assertEqual(len(paths), 17)
        for path in paths:
            with self.subTest(path=path):
                spec = self.parse(path)
                tasks = spec.tasks
                self.assertEqual(len(tasks), 8)
                self.assertEqual([t.name.split('-')[0] for t in tasks],
                                 ['mip', 'select', 'refine1', 'refine2', 'refine3', 'refine4', 'refine5', 'final'])
                self.assertFalse(tasks[0].parents)
                for previous, task in zip(tasks, tasks[1:]):
                    self.assertEqual(task.parents, (previous.name,))
                outputs = {f.path: t.name for t in tasks for f in t.outputs}
                for i, task in enumerate(tasks):
                    for f in task.outputs:
                        self.assertTrue(f.path.startswith(str(self.work)+'/' ))
                    for f in task.inputs:
                        if f.path.startswith(str(self.work)+'/'):
                            self.assertIn(outputs[f.path], [t.name for t in tasks[:i]])
                    if i < 7:
                        self.assertEqual(task.command[0], str(self.source/'NewStructure/build/DataPrep'))
                self.assertIn(str(self.source/'NewStructure/build'), spec.execution.wrapper_args)
                self.assertTrue(tasks[0].inputs[0].path.startswith(str(self.reference)+'/'))
                self.assertIn('/transfer/', tasks[0].inputs[0].path)
                selected = next(f.path for f in tasks[1].outputs if f.role == 'root')
                for stage, task in enumerate(tasks[2:7], 1):
                    self.assertIn('-S', task.command)
                    self.assertIn('-x', task.command)
                    self.assertEqual(task.command[task.command.index('-i')+1], selected)
                    if stage == 1:
                        self.assertNotIn('-k', task.command)
                    else:
                        preceding = next(f.path for f in tasks[stage].outputs if f.role == 'calib')
                        self.assertEqual(task.command[task.command.index('-k')+1], preceding)

    def test_preflight_requires_completed_input_and_verified_build(self):
        spec = self.parse(RECIPES/'ps-e1/Yallfile.legacy')
        build = self.source/'NewStructure/build'
        build.mkdir(parents=True)
        binary = build/'DataPrep'
        binary.write_text('#!/bin/sh\nexit 0\n')
        binary.chmod(0o755)
        library = build/'libLFHCAL.so'
        library.write_text('fixture')
        check_hash = spec.preflight[3]
        self.assertNotEqual(subprocess.run(check_hash, capture_output=True).returncode, 0)
        marker = build/'legacy-build.sha256'
        marker.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p)+'\n' for p in (binary, library)))
        check_input = spec.preflight[5]
        self.assertNotEqual(subprocess.run(check_input).returncode, 0)
        transfer = Path(spec.tasks[0].inputs[0].path)
        transfer.parent.mkdir(parents=True)
        transfer.write_text('fixture')
        for command in spec.preflight:
            subprocess.run(command, cwd=spec.source.parent, check=True)
        wrapper = self.work/'ps-e1/in-calibration-build.sh'
        cwd = subprocess.check_output(['bash', str(wrapper), str(build), 'pwd'], text=True).strip()
        self.assertEqual(cwd, str(build))
        library.write_text('changed')
        self.assertNotEqual(subprocess.run(check_hash, capture_output=True).returncode, 0)

    def test_same_output_root_is_rejected(self):
        self.env['PS_LEGACY_WORK'] = str(self.reference)
        spec = self.parse(RECIPES/'ps-e1/Yallfile.legacy')
        self.assertNotEqual(subprocess.run(spec.preflight[0]).returncode, 0)

if __name__ == '__main__':
    unittest.main()
