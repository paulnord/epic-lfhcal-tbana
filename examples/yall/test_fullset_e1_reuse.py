#!/usr/bin/env python3
"""Check that conversion reuse preserves the FullSetE_1 analysis recipe."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from yall_run.model import load_spec

HERE = Path(__file__).resolve().parent / 'fullset-e1-repro'


class ReuseConvertedTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            'LFHCAL_DATA': '/raw',
            'LFHCAL_CONVERTED': '/previous/converted',
            'LFHCAL_WORK': '/fresh/work',
            'EIC_SHELL': '/not-executed/eic-shell',
        })
        env.start()
        self.addCleanup(env.stop)
        self.original = {t.name: t for t in load_spec(HERE / 'Yallfile').tasks}
        self.reuse = {t.name: t for t in load_spec(HERE / 'Yallfile.after-convert').tasks}

    def test_conversion_is_replaced_by_input_checks(self):
        self.assertEqual(len(self.reuse), 19)
        checks = [t for name, t in self.reuse.items() if name.startswith('reuse-')]
        self.assertEqual(len(checks), 7)
        for task in checks:
            self.assertFalse(task.outputs)
            self.assertEqual(task.parents, ('prepare',))
            self.assertEqual(task.command, ('/usr/bin/test', '-s', task.inputs[0].path))
            self.assertTrue(task.inputs[0].path.startswith('/previous/converted/'))
        self.assertFalse(any(name.startswith('convert-') for name in self.reuse))

    def test_muon_order_and_pedestal_are_preserved(self):
        merge = self.reuse['merge-muon']
        self.assertEqual(tuple(ref.path for ref in merge.inputs),
                         tuple(f'/previous/converted/rawHGCROC_{run}.root' for run in range(373, 379)))
        self.assertEqual(merge.parents, tuple(f'reuse-muon-{run}' for run in range(373, 379)))
        pedestal = self.reuse['pedestal-372']
        self.assertEqual(pedestal.parents, ('reuse-pedestal-372',))
        self.assertEqual(pedestal.inputs[0].path, '/previous/converted/rawHGCROC_372.root')

    def test_old_inputs_are_never_outputs(self):
        for task in self.reuse.values():
            for ref in task.outputs:
                self.assertTrue(ref.path.startswith('/fresh/work/fullset-e1-repro/'), ref.path)
        self.assertEqual(self.reuse['merge-muon'].outputs[0].path,
                         '/fresh/work/fullset-e1-repro/converted/rawHGCROC_Muon_FullSetE_1.root')

    def test_every_analysis_command_and_output_is_unchanged(self):
        substitutions = {
            f'/fresh/work/fullset-e1-repro/converted/rawHGCROC_{run}.root':
            f'/previous/converted/rawHGCROC_{run}.root' for run in range(372, 379)
        }
        for name, original in self.original.items():
            if name.startswith('convert-'):
                continue
            current = self.reuse[name]
            expected = original.command
            if not isinstance(expected, str):
                expected = tuple(substitutions.get(arg, arg) for arg in expected)
            self.assertEqual(current.command, expected, name)
            self.assertEqual(current.outputs, original.outputs, name)
            self.assertEqual(current.parents,
                             tuple(parent.replace('convert-', 'reuse-', 1)
                                   for parent in original.parents), name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
