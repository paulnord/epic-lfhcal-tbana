#!/usr/bin/env python3
"""Check Yallfile graph structure without ROOT, raw data, or a scheduler.

Run with a yall-run checkout supporting multiple named @each sources.
"""
from pathlib import Path
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from yall_run.model import load_spec

EXAMPLES = Path(__file__).resolve().parent
EXPECTED = {'scan-set-1': 56, 'scan-set-2': 188, 'lfhcal-simple': 16}


def pair_rows(text):
    match = re.search(r'^@table pairs ped (run|mip):\n((?:[ \t]+[^\n]*\n)+)', text, re.M)
    if match is None:
        raise AssertionError('missing top-level pairs table')
    return match, [tuple(line.split()) for line in match[2].splitlines()]


class SharedConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            'LFHCAL_DATA': str(Path(self.temp.name) / 'data'),
            'LFHCAL_WORK': str(Path(self.temp.name) / 'work'),
            'EIC_SHELL': '/not-executed/eic-shell',
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def load_text(self, text):
        source = Path(self.temp.name) / 'Yallfile'
        source.write_text(text)
        return {t.name: t for t in load_spec(source).tasks}

    def check_graph(self, which, text):
        _, pairs = pair_rows(text)
        tasks = self.load_text(text)
        runs = list(dict.fromkeys([p for p, _ in pairs] + [m for _, m in pairs]))
        pedestals = list(dict.fromkeys(p for p, _ in pairs))
        self.assertEqual([n for n in tasks if n.startswith('convert-')],
                         ['convert-' + r for r in runs])
        self.assertEqual([n for n in tasks if n.startswith('pedestal-')],
                         ['pedestal-' + p for p in pedestals])
        self.assertNotIn('converted', tasks)
        for run in runs:
            self.assertEqual(tasks['convert-' + run].parents, ('prepare',))
        for ped in pedestals:
            self.assertEqual(tasks['pedestal-' + ped].parents, ('convert-' + ped,))
        stage = 'calibration' if which == 'lfhcal-simple' else 'transfer'
        self.assertEqual([n for n in tasks if n.startswith(stage + '-')],
                         [f'{stage}-{p}-{m}' for p, m in pairs])
        for ped, muon in pairs:
            self.assertEqual(tasks[f'{stage}-{ped}-{muon}'].parents,
                             (f'pedestal-{ped}', f'convert-{muon}'))
            if which == 'lfhcal-simple':
                self.assertEqual(tasks[f'summary-{muon}'].parents, (f'convert-{muon}',))
            else:
                self.assertEqual(tasks[f'mip-{ped}-{muon}'].parents,
                                 (f'transfer-{ped}-{muon}',))
        # Every produced input has an upstream producer, never a hidden race.
        owners = {ref.path: t.name for t in tasks.values() for ref in t.outputs}
        def ancestors(name):
            result = set()
            todo = list(tasks[name].parents)
            while todo:
                parent = todo.pop()
                if parent not in result:
                    result.add(parent)
                    todo.extend(tasks[parent].parents)
            return result
        for task in tasks.values():
            upstream = ancestors(task.name)
            for ref in task.inputs:
                if ref.path in owners:
                    self.assertIn(owners[ref.path], upstream, (task.name, ref.path))
        return tasks

    def test_default_graphs(self):
        for which, count in EXPECTED.items():
            with self.subTest(example=which):
                text = (EXAMPLES / which / 'Yallfile').read_text()
                self.assertEqual(len(self.check_graph(which, text)), count)

    def test_shared_pedestal_is_converted_and_fitted_once(self):
        for which, count in EXPECTED.items():
            with self.subTest(example=which):
                text = (EXAMPLES / which / 'Yallfile').read_text()
                match, rows = pair_rows(text)
                rows[1] = (rows[0][0], rows[1][1])
                text = text[:match.start(2)] + ''.join(f'    {p} {m}\n' for p, m in rows) + text[match.end(2):]
                self.assertEqual(len(self.check_graph(which, text)), count - 2)

    def test_run_in_both_columns_is_converted_once(self):
        for which, count in EXPECTED.items():
            with self.subTest(example=which):
                text = (EXAMPLES / which / 'Yallfile').read_text()
                match, rows = pair_rows(text)
                rows[1] = (rows[0][1], rows[1][1])
                text = text[:match.start(2)] + ''.join(f'    {p} {m}\n' for p, m in rows) + text[match.end(2):]
                self.assertEqual(len(self.check_graph(which, text)), count - 1)

    def test_run_based_output_names_still_reject_multiple_calibrations_of_one_muon(self):
        for which in EXPECTED:
            with self.subTest(example=which):
                text = (EXAMPLES / which / 'Yallfile').read_text()
                match, rows = pair_rows(text)
                rows[1] = (rows[1][0], rows[0][1])
                text = text[:match.start(2)] + ''.join(f'    {p} {m}\n' for p, m in rows) + text[match.end(2):]
                with self.assertRaisesRegex(ValueError, 'owned by both'):
                    self.load_text(text)


if __name__ == '__main__':
    unittest.main()
