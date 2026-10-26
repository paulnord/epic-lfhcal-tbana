"""Prerequisite failures must be visible and precede output creation."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

LAUNCHER=Path(__file__).resolve().parents[1]/'run.sh'

class Prerequisites(unittest.TestCase):
    def check_failure(self, root_config=None, python=False, root_module=None):
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary); binaries=home/'bin'; binaries.mkdir()
            if root_config is not None:
                file=binaries/'root-config';file.write_text('#!/bin/sh\n'+root_config+'\n');file.chmod(0o755)
            if python: (binaries/'python3').symlink_to(sys.executable)
            if root_module is not None: (home/'ROOT.py').write_text(root_module)
            out=home/'must-not-exist'
            environment={**os.environ,'PATH':str(binaries),'PYTHONPATH':str(home)}
            result=subprocess.run(['/bin/bash',str(LAUNCHER),str(home/'campaign'),str(out)],
                                  env=environment,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(out.exists())
            self.assertIn('has not changed your environment or created an output directory',result.stderr)
            return result.stderr

    def test_missing_root_config(self):
        self.assertIn('root-config is not on PATH',self.check_failure())

    def test_missing_python(self):
        self.assertIn('python3 is not on PATH',self.check_failure('printf "6.40.04\\n"'))

    def test_missing_pyroot(self):
        error=self.check_failure('printf "6.40.04\\n"',True,"raise ImportError('test fixture unavailable')\n")
        self.assertIn('python3 cannot import PyROOT',error)

    def test_inconsistent_root_versions(self):
        module="class Version:\n def GetVersion(self): return '6.40/00'\ngROOT=Version()\n"
        self.assertIn('differs from root-config 6.40.04',self.check_failure('printf "6.40.04\\n"',True,module))

    def test_broken_root_config(self):
        module="class Version:\n def GetVersion(self): return '6.40/04'\ngROOT=Version()\n"
        self.assertIn('root-config --version failed',self.check_failure('exit 9',True,module))

if __name__=='__main__': unittest.main()
