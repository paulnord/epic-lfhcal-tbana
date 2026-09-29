"""Exercise sourcing the actual environment helper, without ROOT or Condor."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1]/'example-env.tcsh'
TCSH = shutil.which('tcsh')


@unittest.skipUnless(TCSH, 'tcsh is not installed')
class ExampleEnvStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cwd = self.root/'repo/examples/yall/sample'
        self.cwd.mkdir(parents=True)
        self.work = self.root/'work'
        self.env = {k:v for k,v in os.environ.items()
                    if not k.startswith(('LFHCAL_', 'YALL_', 'EIC_'))}
        self.env.update(LFHCAL_HOME=str(self.root), LFHCAL_WORK=str(self.work),
                        EIC_SHELL='/not-invoked/eic-shell')
        (self.root/'activate.tcsh').write_text('/bin/true\n')

    def source(self, argument='sample'):
        # Capture status immediately, and prove source did not exit its caller.
        script = (f'source "{HELPER}" {argument}\n'
                  'set rc = $status\n'
                  'echo CALLER_SURVIVED\n'
                  'exit $rc\n')
        result = subprocess.run([TCSH, '-f', '-c', script], cwd=self.cwd,
                                env=self.env, text=True, capture_output=True)
        self.assertIn('CALLER_SURVIVED', result.stdout, result.stdout+result.stderr)
        return result

    def test_success_and_work_directories(self):
        result = self.source()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue((self.work/'sample').is_dir())
        self.assertTrue((self.work/'campaigns').is_dir())

    def test_activation_failure_propagates(self):
        (self.root/'activate.tcsh').write_text('/bin/false\n')
        self.assertNotEqual(self.source().returncode, 0)
        self.assertFalse(self.work.exists())

    def test_missing_argument_propagates(self):
        self.assertNotEqual(self.source('').returncode, 0)

    def test_directory_creation_failure_propagates(self):
        self.work.write_text('existing file, do not replace')
        self.assertNotEqual(self.source().returncode, 0)
        self.assertEqual(self.work.read_text(), 'existing file, do not replace')


if __name__ == '__main__':
    unittest.main()
