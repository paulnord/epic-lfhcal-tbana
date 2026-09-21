#!/usr/bin/env python3
"""Check host setup isolation and the reduced FullSetE_1 batch graph."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yall_run.model import load_spec

HERE = Path(__file__).resolve().parent / 'fullset-e1-repro'
spec = importlib.util.spec_from_file_location('prepare_host', HERE / 'prepare_host.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class HostSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='host setup ')
        self.addCleanup(self.temp.cleanup)
        self.converted = Path(self.temp.name) / 'converted'
        self.work = Path(self.temp.name) / 'new work'
        self.converted.mkdir()
        for run in range(372, 379):
            (self.converted / f'rawHGCROC_{run}.root').write_bytes(b'input fixture')
        env = patch.dict(os.environ, {'LFHCAL_CONVERTED': str(self.converted),
                         'LFHCAL_WORK': str(self.work), 'EIC_SHELL': '/not-executed/eic-shell'})
        env.start()
        self.addCleanup(env.stop)
        self.before = {t.name: t for t in load_spec(HERE / 'Yallfile.test-inline-final').tasks}
        self.after = {t.name: t for t in load_spec(HERE / 'Yallfile.test-host-setup').tasks}

    def test_only_bookkeeping_jobs_removed(self):
        self.assertEqual(len(self.after), 10)
        self.assertEqual(set(self.after), {n for n in self.before
                                          if n != 'prepare' and not n.startswith('reuse-')})
        for name, task in self.after.items():
            old = self.before[name]
            self.assertEqual(task.command, old.command, name)
            self.assertEqual(task.inputs, old.inputs, name)
            self.assertEqual(task.outputs, old.outputs, name)
            expected = () if name in ('merge-muon', 'pedestal-372') else old.parents
            self.assertEqual(task.parents, expected, name)

    def test_host_creates_output_parents_without_declared_outputs(self):
        result = setup.prepare(self.converted, self.work)
        self.assertTrue((self.work / 'host-setup.json').is_file())
        self.assertTrue((self.work / 'campaigns').is_dir())
        for task in self.after.values():
            for ref in task.outputs:
                self.assertTrue(Path(ref.path).parent.is_dir(), ref.path)
                self.assertFalse(Path(ref.path).exists(), ref.path)
        for source in self.converted.glob('*.root'):
            self.assertEqual(source.read_bytes(), b'input fixture')
        self.assertEqual(result, (self.work / 'fullset-e1-repro').resolve())

    def test_missing_input_creates_nothing(self):
        (self.converted / 'rawHGCROC_378.root').unlink()
        with self.assertRaisesRegex(ValueError, '378'):
            setup.prepare(self.converted, self.work)
        self.assertFalse(self.work.exists())

    def test_used_output_root_is_rejected(self):
        setup.prepare(self.converted, self.work)
        retained = self.work / 'fullset-e1-repro/refine5/keep.root'
        retained.write_bytes(b'previous result')
        with self.assertRaisesRegex(ValueError, 'fresh LFHCAL_WORK'):
            setup.prepare(self.converted, self.work)
        self.assertEqual(retained.read_bytes(), b'previous result')

    def test_output_inside_inputs_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            setup.prepare(self.converted, self.converted / 'new work')
        self.assertFalse((self.converted / 'new work').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
