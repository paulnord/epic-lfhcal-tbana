#!/usr/bin/env python3
"""Check Yallfile graph structure without ROOT, raw data, or a scheduler.

Run with a yall-run checkout containing yall-run PR #33's partial ``@each``
binding support (merged as 1081e9dd39418262588248272618130ce0503b8a).
"""
from pathlib import Path
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from yall_run.model import load_spec

EXAMPLES = Path(__file__).resolve().parent
EXPECTED = {'scan-set-1': 56, 'scan-set-2': 188, 'lfhcal-simple': 10}
FULLSET_EXPECTED = {
    'fullset-b1-repro': 26,
    'fullset-b2-repro': 20,
    'fullset-c1-repro': 25,
    'fullset-c2-repro': 19,
    'fullset-c3-repro': 18,
    'fullset-d1-repro': 30,
    'fullset-d2-repro': 18,
    'fullset-e1-repro': 19,
    'fullset-e2-repro': 18,
    'fullset-e3-repro': 19,
    'fullset-f1-repro': 18,
    'fullset-f2-repro': 19,
    'fullset-g1-repro': 20,
    'fullset-g2-repro': 21,
}
FULLSET_SUFFIX = {
    'fullset-b1-repro': 'b1',
    'fullset-b2-repro': 'b2',
    'fullset-c1-repro': 'c1',
    'fullset-c2-repro': 'c2',
    'fullset-c3-repro': 'c3',
    'fullset-d1-repro': 'd1',
    'fullset-d2-repro': 'd2',
    'fullset-e1-repro': 'e1',
    'fullset-e2-repro': 'e2',
    'fullset-e3-repro': 'e3',
    'fullset-f1-repro': 'f1',
    'fullset-f2-repro': 'f2',
    'fullset-g1-repro': 'g1',
    'fullset-g2-repro': 'g2',
}
RUNDB_NAME = 'DataTakingDB_TBSPSH2_202605_HGCROC.csv'
HVSCAN_MUONS = ('194', '195', '196', '197', '198', '199', '200', '201', '202')
HVSCAN_EXPECTED = 93


def pair_rows(text):
    match = re.search(r'^@table pairs ped (run|mip):\n((?:[ \t]+[^\n]*\n)+)', text, re.M)
    if match is None:
        raise AssertionError('missing top-level pairs table')
    return match, [tuple(line.split()) for line in match[2].splitlines()]


def run_rows(text):
    match = re.search(r'^@table runs type run:\n((?:[ \t]+[^\n]*\n)+)', text, re.M)
    if match is None:
        raise AssertionError('missing top-level typed runs table')
    return match, [tuple(line.split()) for line in match[1].splitlines()]


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

        if which == 'lfhcal-simple':
            self.assertFalse(any(n.startswith('calibration-') for n in tasks))
            self.assertFalse(any(n.startswith('summary-') for n in tasks))
        else:
            stage = 'transfer'
            self.assertEqual([n for n in tasks if n.startswith(stage + '-')],
                             [f'{stage}-{p}-{m}' for p, m in pairs])
            for ped, muon in pairs:
                self.assertEqual(tasks[f'{stage}-{ped}-{muon}'].parents,
                                 (f'pedestal-{ped}', f'convert-{muon}'))
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

    def check_fullset_graph(self, which, text):
        _, rows = run_rows(text)
        tasks = self.load_text(text)
        pedestal_runs = [run for run_type, run in rows if run_type == 'pedestal']
        muon_runs = [run for run_type, run in rows if run_type == 'muon']
        self.assertEqual(len(pedestal_runs), 1, (which, rows))
        self.assertTrue(muon_runs, (which, rows))

        conversions = [f'convert-{run_type}-{run}' for run_type, run in rows]
        self.assertEqual([name for name in tasks if name.startswith('convert-')],
                         conversions)
        for name in conversions:
            self.assertEqual(tasks[name].parents, ('prepare',), (which, name))

        muon_parents = tuple(f'convert-muon-{run}' for run in muon_runs)
        self.assertEqual(tasks['merge-muon'].parents, muon_parents)
        merge_inputs = tuple(Path(ref.path).name for ref in tasks['merge-muon'].inputs)
        self.assertEqual(merge_inputs,
                         tuple(f'rawHGCROC_{run}.root' for run in muon_runs))
        self.assertNotIn(
            f'rawHGCROC_{pedestal_runs[0]}.root',
            merge_inputs,
            (which, 'pedestal conversion leaked into merge-muon'),
        )

        pedestal_run = pedestal_runs[0]
        pedestal_name = f'pedestal-{pedestal_run}'
        self.assertEqual(tasks[pedestal_name].parents,
                         (f'convert-pedestal-{pedestal_run}',))
        self.assertTrue(any(
            Path(ref.path).name == f'rawHGCROC_{pedestal_run}.root'
            for ref in tasks[pedestal_name].inputs
        ))

        transfer = tasks[f'transfer-{FULLSET_SUFFIX[which]}']
        self.assertEqual(transfer.parents,
                         ('merge-muon', pedestal_name))
        pedestal_outputs = {ref.path for ref in tasks[pedestal_name].outputs}
        transfer_inputs = {ref.path for ref in transfer.inputs}
        self.assertEqual(len(pedestal_outputs & transfer_inputs), 1,
                         (which, pedestal_outputs, transfer_inputs))
        return tasks

    def test_default_graphs(self):
        for which, count in EXPECTED.items():
            with self.subTest(example=which):
                text = (EXAMPLES / which / 'Yallfile').read_text()
                self.assertEqual(len(self.check_graph(which, text)), count)

    def test_fullset_graphs(self):
        for which, count in FULLSET_EXPECTED.items():
            with self.subTest(example=which):
                text = (EXAMPLES / which / 'Yallfile').read_text()
                self.assertEqual(len(self.check_fullset_graph(which, text)), count)

    def test_fullset_pedestal_dependencies_follow_run_table(self):
        for which, count in FULLSET_EXPECTED.items():
            with self.subTest(example=which):
                text = (EXAMPLES / which / 'Yallfile').read_text()
                match, rows = run_rows(text)
                old_run = next(run for run_type, run in rows
                               if run_type == 'pedestal')
                new_run = str(int(old_run) + 1000)
                changed_rows = [
                    (run_type, new_run if run_type == 'pedestal' else run)
                    for run_type, run in rows
                ]
                replacement = ''.join(
                    f'    {run_type:<8} {run}\n'
                    for run_type, run in changed_rows
                )
                text = text[:match.start(1)] + replacement + text[match.end(1):]
                tasks = self.check_fullset_graph(which, text)
                self.assertEqual(len(tasks), count)
                self.assertIn(f'convert-pedestal-{new_run}', tasks)
                self.assertIn(f'pedestal-{new_run}', tasks)
                self.assertNotIn(f'convert-pedestal-{old_run}', tasks)
                self.assertNotIn(f'pedestal-{old_run}', tasks)

    def test_hvscan_graph(self):
        text = (EXAMPLES / 'hvscan-repro' / 'Yallfile').read_text()
        tasks = self.load_text(text)
        self.assertEqual(len(tasks), HVSCAN_EXPECTED)
        self.assertEqual(tasks['pedestal-188'].parents, ('convert-pedestal-188',))
        self.assertEqual(
            [name for name in tasks if name.startswith('convert-')],
            ['convert-pedestal-188'] + [f'convert-muon-{run}' for run in HVSCAN_MUONS],
        )
        for run in HVSCAN_MUONS:
            self.assertEqual(
                tasks[f'transfer-muon-{run}'].parents,
                (f'convert-muon-{run}', 'pedestal-188'),
            )
            self.assertEqual(
                tasks[f'final-muon-{run}'].parents,
                (f'refine5-muon-{run}',),
            )

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
        for which in ('scan-set-1', 'scan-set-2'):
            with self.subTest(example=which):
                text = (EXAMPLES / which / 'Yallfile').read_text()
                match, rows = pair_rows(text)
                rows[1] = (rows[1][0], rows[0][1])
                text = text[:match.start(2)] + ''.join(f'    {p} {m}\n' for p, m in rows) + text[match.end(2):]
                with self.assertRaisesRegex(ValueError, 'owned by both'):
                    self.load_text(text)

    def test_dataprep_stages_pass_run_database(self):
        cases = {
            'lfhcal-simple': ('pedestal-296',),
            'calibration-pair': ('pedestal', 'mip'),
        }
        for which, names in cases.items():
            with self.subTest(example=which):
                text = (EXAMPLES / which / 'Yallfile').read_text()
                tasks = self.load_text(text)
                for name in names:
                    task = tasks[name]
                    command = task.command if isinstance(task.command, str) else ' '.join(task.command)
                    self.assertRegex(command, r'(?:^|\s)-r\s+', (which, name, command))
                    self.assertTrue(
                        any(Path(ref.path).name == RUNDB_NAME for ref in task.inputs),
                        (which, name),
                    )


if __name__ == '__main__':
    unittest.main()
