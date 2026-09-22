#!/usr/bin/env python3
"""Check restart isolation and unchanged refinement commands."""
import importlib.util
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch
from yall_run.model import load_spec

HERE = Path(__file__).resolve().parent/'fullset-e1-repro'
spec = importlib.util.spec_from_file_location('prepare_after_mip', HERE/'prepare_after_mip.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class AfterMipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='after mip ')
        self.addCleanup(self.tmp.cleanup)
        self.previous = Path(self.tmp.name)/'previous'
        self.work = Path(self.tmp.name)/'new work'
        paths = [f'mip/{setup.MIP}.root', f'mip/{setup.MIP}_calib.txt',
                 f'mip/{setup.MIP}_Hists.root', f'selected/{setup.SELECTED}', f'final/{setup.FINAL}']
        for name in paths:
            p = self.previous/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(name.encode())
        self.original = {str(p): p.read_bytes() for p in self.previous.rglob('*') if p.is_file()}
        env = patch.dict(os.environ, {'LFHCAL_PREVIOUS': str(self.previous),
                         'LFHCAL_CONVERTED': '/unused', 'LFHCAL_WORK': str(self.work),
                         'EIC_SHELL': '/not-executed/eic-shell'})
        env.start()
        self.addCleanup(env.stop)

    def test_six_jobs_retain_all_refinement_commands(self):
        old = {t.name: t for t in load_spec(HERE/'Yallfile.test-host-setup').tasks}
        new = {t.name: t for t in load_spec(HERE/'Yallfile.after-mip').tasks}
        self.assertEqual(set(new), {'select-e1'} | {f'refine{i}-e1' for i in range(1, 6)})
        self.assertFalse(new['select-e1'].parents)
        for n in range(1, 6):
            name = f'refine{n}-e1'
            for attr in ('command', 'inputs', 'outputs', 'parents'):
                self.assertEqual(getattr(new[name], attr), getattr(old[name], attr), (name, attr))
        select = new['select-e1']
        args = shlex.split(select.command.split(' && ', 1)[0])
        self.assertEqual(args[args.index('-i')+1], str(self.previous/'mip'/f'{setup.MIP}.root'))
        self.assertIn('-X', args)
        self.assertIn('compare_skim.C', select.command)
        setup.prepare(self.previous, self.work)
        for task in new.values():
            for output in task.outputs:
                self.assertTrue(Path(output.path).parent.is_dir(), output.path)
                self.assertFalse(Path(output.path).exists(), output.path)

    def test_copies_small_comparison_inputs_preserves_originals(self):
        result = setup.prepare(self.previous, self.work)
        self.assertFalse((result/'mip'/f'{setup.MIP}.root').exists())
        self.assertEqual((result/'mip'/f'{setup.MIP}_calib.txt').read_bytes(),
                         (self.previous/'mip'/f'{setup.MIP}_calib.txt').read_bytes())
        self.assertEqual((result/'baseline'/setup.FINAL).read_bytes(),
                         (self.previous/'final'/setup.FINAL).read_bytes())
        self.assertTrue((self.work/'after-mip-setup.json').is_file())
        self.assertEqual(self.original, {str(p): p.read_bytes() for p in self.previous.rglob('*') if p.is_file()})

    def test_missing_event_input_creates_nothing(self):
        (self.previous/'mip'/f'{setup.MIP}.root').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing'):
            setup.prepare(self.previous, self.work)
        self.assertFalse(self.work.exists())

    def test_existing_output_is_rejected(self):
        setup.prepare(self.previous, self.work)
        with self.assertRaisesRegex(ValueError, 'fresh'):
            setup.prepare(self.previous, self.work)

    def test_overlapping_directories_are_rejected(self):
        for target in (self.previous, self.previous/'nested', self.previous.parent):
            with self.assertRaisesRegex(ValueError, 'separate'):
                setup.prepare(self.previous, target)


if __name__ == '__main__':
    unittest.main(verbosity=2)
