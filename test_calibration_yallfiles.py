"""Offline scientific wiring checks, using the actual yall-run parser.

Run from the repository root: python3 -m unittest -v test_calibration_yallfiles.py
Requires yall-run on the Python path; does not need ROOT or raw data.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import prepare_calibration_yallfiles as setup
from yall_run.model import load_spec

CATALOG = Path(__file__).parent/'examples/yall/calibration-2026/calibration_2026_sets.json'
if not CATALOG.exists():
    CATALOG = Path(__file__).with_name('calibration_2026_sets.json')


def flag(command, name):
    return command[command.index(name)+1]


class Recipes(unittest.TestCase):
    def setUp(self):
        self.recipes = json.loads(CATALOG.read_text())['sets']
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def parse(self, name, n=5):
        path = self.root/name
        path.mkdir(exist_ok=True)
        file = path/'Yallfile'
        file.write_text(setup.render(name, self.recipes[name], self.root, Path('/raw'), Path('/source'), Path('/eic-shell'), refinements=n))
        return load_spec(file)

    def test_all_sets_expansion_and_inputs_have_upstream_producers(self):
        for name, r in self.recipes.items():
            with self.subTest(name=name):
                spec = self.parse(name)
                by_name = {t.name: t for t in spec.tasks}
                owners = {f.path: t.name for t in spec.tasks for f in t.outputs}
                def ancestors(t):
                    result = set(t.parents)
                    for p in t.parents:
                        result.update(ancestors(by_name[p]))
                    return result
                for t in spec.tasks:
                    for f in t.inputs:
                        if f.path.startswith(str(self.root)):
                            self.assertIn(f.path, owners)
                            self.assertIn(owners[f.path], ancestors(t), (t.name, f.path))
                self.assertEqual(len([t for t in spec.tasks if t.name.startswith('final-')]),
                                 1 if r['campaign'] == 'ps' else len(r['pedestal_muon_pairs']))
                conversion = [t for t in spec.tasks if t.name.startswith('convert-')]
                self.assertEqual(len(conversion), len(r['muon_runs'])+len(r['pedestal_runs'])+len(r.get('extra_raw_runs', [])))
                for t in conversion:
                    self.assertTrue(flag(t.command, '-c').endswith('Run'+t.name.rsplit('-', 1)[1]+'.h2g'))
                for t in [t for t in spec.tasks if t.name.startswith('refine')]:
                    stage = int(t.name.split('-', 1)[0][6:])
                    self.assertIn('-x', t.command)
                    self.assertIn('-S', t.command)
                    self.assertIn('/select/', flag(t.command, '-i'))
                    if stage == 1:
                        self.assertNotIn('-k', t.command)
                    else:
                        self.assertIn('/refine%d/' % (stage-1), flag(t.command, '-k'))
                        self.assertEqual(t.parents, ('refine%d-' % (stage-1)+t.name.split('-', 1)[1],))

    def test_ps_merge_excludes_pedestals_and_preserves_requested_muons(self):
        for name, r in self.recipes.items():
            if r['campaign'] != 'ps':
                continue
            spec = self.parse(name)
            merge = next(t for t in spec.tasks if t.name == 'merge-muon')
            self.assertEqual(set(merge.parents), {'convert-muon-%03d' % x for x in r['muon_runs']})
            self.assertEqual(len(merge.command)-3, len(r['muon_runs']))
            self.assertNotIn('rawHGCROC_%03d.root' % r['pedestal_runs'][0], ' '.join(merge.command))

    def test_sps_never_merges_scan_settings_or_calibrates_unpaired_runs(self):
        for name in ('sps-param1', 'sps-param2', 'sps-param3'):
            spec = self.parse(name)
            self.assertFalse(any(t.name.startswith('merge') for t in spec.tasks))
            for p in self.recipes[name]['pedestal_muon_pairs']:
                t = next(t for t in spec.tasks if t.name == 'transfer-%03d-%03d' % (p['pedestal'], p['muon']))
                self.assertEqual(t.parents, ('convert-muon-%03d' % p['muon'], 'pedestal-%03d' % p['pedestal']))
            for run in self.recipes[name].get('extra_raw_runs', []):
                self.assertFalse(any(t.name.startswith('transfer-') and t.name.endswith('-%03d' % run) for t in spec.tasks))

    def test_uncertain_associations_remain_drafts_until_explicitly_supplied(self):
        self.assertEqual(sum(not r['review_needed'] for r in self.recipes.values()), 9)
        setup.apply_overrides(self.recipes, {'ps-a2': {'pedestal': 120}})
        self.assertTrue(self.recipes['ps-a2']['review_needed'])
        setup.apply_overrides(self.recipes, {'ps-a2': {'toa': 'none'}})
        self.assertFalse(self.recipes['ps-a2']['review_needed'])
        t = next(t for t in self.parse('ps-a2').tasks if t.name.startswith('transfer-'))
        self.assertNotIn('-G', t.command)
        self.assertIn('rawHGCROC_wPed_120.root', flag(t.command, '-P'))
        self.assertEqual(self.recipes['ps-d1']['pedestal_runs'], [238])
        self.assertEqual(self.recipes['ps-g1']['pedestal_runs'], [379])

    def test_refinement_count_and_input_path_injection(self):
        for n in (1, 4, 8):
            spec = self.parse('ps-c1', n)
            t = next(t for t in spec.tasks if t.name.startswith('final-'))
            self.assertTrue(t.parents[0].startswith('refine%d-' % n))
        for path in ('/data/with space', '/data/$(bad)', '/data/{unknown}', '/data/quote\"'):
            with self.assertRaises(ValueError):
                setup.safe_path(path)
        with self.assertRaises(ValueError):
            setup.apply_overrides(self.recipes, {'ps-a1': {'pedestal': 86}})


if __name__ == '__main__':
    unittest.main()
