"""ROOT-free checks of the D1-only recovery preparation and source edits."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import recover_adaptive_d1 as r


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Missing or ambiguous pinned anchor')
    return source.replace(old, new, 1)


# The source edits are matched to exact anchors of the pinned launcher.
FIXTURE = '''
EXTENSION = {'transfer': {}}
def run(command, cwd, log, timeout=10800, env=None):
    return timeout

def stage_command(out, model, code, stage, exe):
    return [exe, '-s', '-i', 'same_input', '-o', 'new_output']

def yallfile(out):
    return ['campaign lfhcal-minimal-adaptive-fullchains-extension', '%time 4h']

def prepare(args):
    inputs={c:find_inputs(c,args.work.resolve(),args.archive.resolve(),args.data.resolve()) for c in SPECS}
    return inputs

def common_input(out, code):
    work, transfer, trees, incoming = None, None, None, {'mode': 'transfer'}
    dump(work/'ready.json',dict(transfer=file_info(transfer,hashed=True),trees=trees,
                              boundary='before initial MIP calibration',mode=incoming['mode']))
'''


class RecoveryTests(unittest.TestCase):
    def previous(self, root):
        old = root/'old'
        old.mkdir()
        self.save(old/'manifest.json', dict(base_commit='base', kit_commit='kit', specs={'d1': {}}))
        for model in ('legacy', 'adaptive'):
            self.save(old/model/'d1'/'mip'/'DataPrep.log.json',
                      dict(outcome='timeout', timeout_s=10800, returncode=-15))
        source = root/'pre-mip.root'
        source.write_bytes(b'pre-mip test input')
        self.save(old/'inputs'/'d1'/'ready.json', dict(boundary='before initial MIP calibration',
            transfer=dict(path=str(source.resolve()), size=source.stat().st_size,
                mtime_ns=source.stat().st_mtime_ns, sha256=hashlib.sha256(source.read_bytes()).hexdigest())))
        return old, source

    @staticmethod
    def save(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def test_confirmed_two_timeouts_and_input(self):
        with tempfile.TemporaryDirectory() as d:
            old, source = self.previous(Path(d))
            data, info, evidence = r.inspect_previous(old, 'base', 'kit')
            self.assertEqual(set(evidence), {'legacy', 'adaptive'})
            self.assertEqual(info['path'], str(source))
            self.assertIn('d1', data['specs'])

    def test_does_not_touch_old_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            old, _ = self.previous(Path(d))
            partial = old/'legacy/d1/mip/partial.root'
            partial.write_bytes(b'incomplete')
            before = {str(p):p.read_bytes() for p in old.rglob('*') if p.is_file()}
            r.inspect_previous(old, 'base', 'kit')
            self.assertEqual(before, {str(p):p.read_bytes() for p in old.rglob('*') if p.is_file()})

    def test_completed_stage_refused(self):
        with tempfile.TemporaryDirectory() as d:
            old, _ = self.previous(Path(d))
            self.save(old/'adaptive/d1/mip/stage.json', {})
            with self.assertRaisesRegex(ValueError, 'already'):
                r.inspect_previous(old, 'base', 'kit')

    def test_not_general_retry_for_arbitrary_errors(self):
        with tempfile.TemporaryDirectory() as d:
            old, _ = self.previous(Path(d))
            self.save(old/'adaptive/d1/mip/DataPrep.log.json', dict(outcome='failed', timeout_s=10800))
            with self.assertRaisesRegex(ValueError, 'confirmed'):
                r.inspect_previous(old, 'base', 'kit')

    def test_fitter_version_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as d:
            old, _ = self.previous(Path(d))
            with self.assertRaisesRegex(ValueError, 'Different fitter'):
                r.inspect_previous(old, 'different', 'kit')

    def test_changed_input_refused(self):
        with tempfile.TemporaryDirectory() as d:
            old, source = self.previous(Path(d))
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'metadata changed'):
                r.inspect_previous(old, 'base', 'kit')

    def test_selected_input_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            old, _ = self.previous(Path(d))
            path = old/'inputs/d1/ready.json'
            data = r.read(path); data['boundary'] = 'after MIP skim'
            self.save(path, data)
            with self.assertRaisesRegex(ValueError, 'pre-MIP'):
                r.inspect_previous(old, 'base', 'kit')

    def test_output_file_not_accepted_as_input(self):
        with tempfile.TemporaryDirectory() as d:
            old, source = self.previous(Path(d))
            partial = old/'adaptive/d1/mip/partial.root'; partial.write_bytes(source.read_bytes())
            path = old/'inputs/d1/ready.json'; data = r.read(path)
            data['transfer']['path'] = str(partial)
            self.save(path, data)
            with self.assertRaisesRegex(ValueError, 'fit output'):
                r.inspect_previous(old, 'base', 'kit')

    def test_pinned_hash_required(self):
        with tempfile.TemporaryDirectory() as d:
            old, _ = self.previous(Path(d))
            path = old/'inputs/d1/ready.json'; data = r.read(path)
            del data['transfer']['sha256']; self.save(path, data)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                r.inspect_previous(old, 'base', 'kit')

    def test_eight_hour_child_ten_hour_scheduler(self):
        changed = r.change_budgets(FIXTURE, SimpleNamespace(once=once))
        namespace = {}; exec(changed, namespace)
        self.assertEqual(namespace['run'](None, None, None), r.CHILD_SECONDS)
        self.assertEqual(r.CHILD_SECONDS, 28800)
        self.assertIn('%time 10h', namespace['yallfile'](None))
        self.assertEqual(r.SCHEDULER_HOURS, 10)
        self.assertIn("checked['sha256'] != EXTENSION['transfer']['sha256']", changed)
        self.assertEqual(namespace['prepare'](None), {'d1': {'mode':'transfer', 'files':{'transfer':{}}}})

    def test_stage_commands_not_edited(self):
        changed = r.change_budgets(FIXTURE, SimpleNamespace(once=once))
        def find(text):
            return ast.dump(next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name=='stage_command'))
        self.assertEqual(find(FIXTURE), find(changed))

    def test_missing_anchors_rejected(self):
        with self.assertRaises(ValueError):
            r.change_budgets(FIXTURE.replace('timeout=10800, env=None', 'timeout=5, env=None'), SimpleNamespace(once=once))

    def test_double_patch_refused(self):
        changed = r.change_budgets(FIXTURE, SimpleNamespace(once=once))
        with self.assertRaises(ValueError):
            r.change_budgets(changed, SimpleNamespace(once=once))


if __name__ == '__main__':
    unittest.main()
