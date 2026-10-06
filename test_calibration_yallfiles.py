"""Offline scientific wiring checks, using the actual yall-run parser.

Run from the repository root: python3 -m unittest -v test_calibration_yallfiles.py
Requires yall-run on the Python path; does not need ROOT or raw data.
"""
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest

from unittest.mock import patch
try:
    from yall_run.model import load_spec
except ModuleNotFoundError as error:
    if error.name != 'yall_run':
        raise
    raise unittest.SkipTest('Install yall-run to validate the native Yallfiles')

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

    def parse(self, name):
        directory = CATALOG.parent/'recipes'/name
        file = directory/('Yallfile.draft' if self.recipes[name]['review_needed'] else 'Yallfile')
        with patch.dict(os.environ, {'CALWORK': str(self.root), 'LFHCAL_SOURCE': str(self.root/'source'),
                                     'LFHCAL_RAW': '/raw', 'EIC_SHELL': '/bin/true'}):
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
                        if f.path.startswith(str(self.root/name)+'/'):
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

    def test_drafts_are_separate_from_complete_yallfiles(self):
        self.assertEqual(sum(not r['review_needed'] for r in self.recipes.values()), 9)
        for name,r in self.recipes.items():
            directory = CATALOG.parent/'recipes'/name
            if r['review_needed']:
                self.assertFalse((directory/'Yallfile').exists())
                self.assertTrue((directory/'Yallfile.draft').exists())
            spec = self.parse(name)
            self.assertFalse(any('prepare_calibration_yallfiles' in str(t.command) for t in spec.tasks))
        self.assertEqual(self.recipes['ps-d1']['pedestal_runs'], [238])
        self.assertEqual(self.recipes['ps-g1']['pedestal_runs'], [379])

    def test_preflight_creates_output_parents_and_uses_existing_build(self):
        build = self.root/'source/NewStructure/build'
        build.mkdir(parents=True)
        for name in ('Convert','DataPrep'):
            file = build/name
            file.write_text('#!/bin/sh\nexit 0\n')
            file.chmod(0o755)
        (build/'libLFHCAL.so').touch()
        spec = self.parse('ps-c1')
        self.assertEqual(len(spec.preflight), 6)
        self.assertFalse(any(t.name in ('build','prepare') for t in spec.tasks))
        self.assertFalse(any('cmake' in str(c) for c in [*spec.preflight,*[t.command for t in spec.tasks]]))
        for command in spec.preflight:
            subprocess.run(command, cwd=spec.source.parent, check=True)
        work = self.root/'ps-c1'
        self.assertTrue((work/'refine5').is_dir())
        self.assertTrue((work/'plots/pedestal').is_dir())
        self.assertTrue((work/'in-calibration-build.sh').is_file())
        self.assertFalse((work/'build').exists())
        wrapper = work/'in-calibration-build.sh'
        result = subprocess.check_output(['bash',str(wrapper),str(build),'/bin/pwd'],text=True).strip()
        self.assertEqual(Path(result),build)
        (build/'Convert').unlink()
        self.assertNotEqual(subprocess.run(spec.preflight[0],cwd=spec.source.parent).returncode,0)

    def test_toa_is_only_an_input_when_an_offset_file_is_assigned(self):
        for name, r in self.recipes.items():
            for task in self.parse(name).tasks:
                if not task.name.startswith('transfer-'):
                    continue
                self.assertEqual('-G' in task.command, r['toa'] is not None)
                self.assertEqual(any(f.role == 'toa' for f in task.inputs), r['toa'] is not None)
                self.assertNotIn('UNASSIGNED_TOA_', str(task))


if __name__ == '__main__':
    unittest.main()
