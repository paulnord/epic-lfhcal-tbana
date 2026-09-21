#!/usr/bin/env python3
"""Verify the experimental final export runs only after refine5 succeeds."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from yall_run.model import load_spec

HERE = Path(__file__).resolve().parent / 'fullset-e1-repro'


class InlineFinalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='inline final ')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name) / 'work with spaces'
        env = patch.dict(os.environ, {
            'LFHCAL_CONVERTED': '/previous/converted',
            'LFHCAL_WORK': str(self.work), 'EIC_SHELL': '/not-executed/eic-shell',
        })
        env.start()
        self.addCleanup(env.stop)
        self.original = {t.name: t for t in load_spec(HERE / 'Yallfile.after-convert').tasks}
        self.test = {t.name: t for t in load_spec(HERE / 'Yallfile.test-inline-final').tasks}

    def test_graph_and_outputs(self):
        self.assertEqual(len(self.test), 18)
        self.assertNotIn('final-e1', self.test)
        for name, task in self.test.items():
            before = self.original[name]
            self.assertEqual(task.parents, before.parents, name)
            self.assertEqual(task.inputs, before.inputs, name)
            if name != 'refine5-e1':
                self.assertEqual(task.command, before.command, name)
                self.assertEqual(task.outputs, before.outputs, name)
        expected = {r.path for t in self.original.values() for r in t.outputs}
        actual = [r.path for t in self.test.values() for r in t.outputs]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(set(actual)))
        command = self.test['refine5-e1'].command
        self.assertEqual(shlex.split(command.split(' && ', 1)[0]),
                         list(self.original['refine5-e1'].command))

    def run_refine5(self, exit_code):
        executable = Path(self.temp.name) / 'fake DataPrep'
        executable.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
p = Path(sys.argv[sys.argv.index('-o') + 1])
p.parent.mkdir(parents=True, exist_ok=True)
p.write_bytes(b'ROOT fixture\\x00\\n')
p.with_name(p.stem + '_calib.txt').write_text('calibration fixture\\n')
sys.exit(int(os.environ['FAKE_FIT_EXIT']))
''')
        executable.chmod(0o755)
        command = self.test['refine5-e1'].command.replace(
            '../../../NewStructure/build/DataPrep', shlex.quote(str(executable)), 1)
        return subprocess.run(['/bin/sh', '-c', command], timeout=10,
                              env={**os.environ, 'FAKE_FIT_EXIT': str(exit_code)},
                              capture_output=True, text=True)

    def test_success_copies_both_outputs(self):
        result = self.run_refine5(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        outputs = {r.role: Path(r.path) for r in self.test['refine5-e1'].outputs}
        self.assertEqual(outputs['root'].read_bytes(), outputs['final_root'].read_bytes())
        self.assertEqual(outputs['calib'].read_bytes(), outputs['final_calib'].read_bytes())

    def test_failure_does_not_export_partial_outputs(self):
        result = self.run_refine5(7)
        self.assertEqual(result.returncode, 7, result.stderr)
        outputs = {r.role: Path(r.path) for r in self.test['refine5-e1'].outputs}
        self.assertTrue(outputs['root'].exists())
        self.assertFalse(outputs['final_root'].exists())
        self.assertFalse(outputs['final_calib'].exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
