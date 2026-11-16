import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('recover_rf7', Path(__file__).with_name('recover_rf7.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.raw = self.root / 'raw'
        self.raw.mkdir()
        for n in (330, 331):
            (self.raw / f'Run{n}.h2g').write_text('synthetic fixture')
        self.eic = self.root / 'eic-shell'
        self.eic.write_text('#!/bin/sh\n')
        self.eic.chmod(0o700)
        self.addCleanup(self.tmp.cleanup)

    def test_missing_raw_rejected_before_creation(self):
        (self.raw / 'Run331.h2g').unlink()
        with self.assertRaisesRegex(ValueError, 'Run331'):
            m.recover(self.root, self.raw, self.eic)
        self.assertEqual([], list(self.root.glob('ari-rf7-*')))

    def test_relative_and_spaces_rejected(self):
        for p in (Path('relative'), self.root / 'has space'):
            with self.assertRaisesRegex(ValueError, 'absolute shared'):
                m.check_inputs(p, self.raw, self.eic)

    def test_missing_host_tool(self):
        with patch.object(m.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'command not found'):
                m.check_inputs(self.root, self.raw, self.eic)

    def exercise(self, submit=False, fail_start=False):
        commands = []
        calls = []
        def fake_run(command, cwd=None, capture=False):
            command = list(map(str, command))
            commands.append(command)
            if command[:2] == ['git', 'clone']:
                Path(command[-1]).mkdir()
            if fail_start and command[:2] == ['yall-run', 'start']:
                raise subprocess.CalledProcessError(1, command)
            output = m.SOURCE if 'rev-parse' in command else '/test/campaign' if command[:2] == ['yall-run', 'create'] else 'synthetic plan\n'
            return subprocess.CompletedProcess(command, 0, stdout=output)
        def prepare(work, raw, eic, mode, ack, **kwargs):
            work.mkdir()
            calls.append((raw, eic, mode, ack, kwargs))
        with patch.object(m.shutil, 'which', return_value='/bin/stub'), patch.object(m, 'run', side_effect=fake_run), patch.object(m.runpy, 'run_path', return_value={'prepare': prepare}):
            if fail_start:
                with self.assertRaises(subprocess.CalledProcessError):
                    m.recover(self.root, self.raw, self.eic, submit)
            else:
                base = m.recover(self.root, self.raw, self.eic, submit)
                self.assertTrue((base / 'work/plan.txt').is_file())
        self.assertEqual(calls[0][-1]['pairs_override'], [(330,331,2)])
        self.assertEqual(sum(c[:2] == ['yall-run','start'] for c in commands), int(submit))
        return commands

    def test_prepare_never_submits(self):
        commands = self.exercise()
        self.assertFalse(any(c[:2] == ['yall-run','create'] for c in commands))

    def test_submit_once(self):
        self.exercise(submit=True)

    def test_failed_submission_not_retried(self):
        self.exercise(submit=True, fail_start=True)


if __name__ == '__main__':
    unittest.main()
