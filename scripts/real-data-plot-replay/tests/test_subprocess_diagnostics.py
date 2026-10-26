"""Subprocess errors must show the saved scientific guard message, not hide it."""
import ast
import contextlib
import io
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'run.py'

class SubprocessDiagnostics(unittest.TestCase):
    def setUp(self):
        definition=next(n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='run')
        scope=dict(shlex=shlex,subprocess=subprocess,sys=sys)
        exec(compile(ast.Module(body=[definition],type_ignores=[]),str(SOURCE),'exec'),scope)
        self.run_logged=scope['run']

    def test_failed_guard_visible_and_exit_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'run.log'; stderr=io.StringIO()
            with contextlib.redirect_stderr(stderr),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(subprocess.CalledProcessError) as failure:
                    self.run_logged([sys.executable,'-c','import sys;print("ERROR: test guard",file=sys.stderr);sys.exit(2)'],log)
            self.assertEqual(failure.exception.returncode,2)
            self.assertIn('ERROR: test guard',stderr.getvalue())
            self.assertIn(str(log),stderr.getvalue())
            self.assertEqual(log.read_text(),'ERROR: test guard\n')

    def test_success_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'run.log'; stderr=io.StringIO()
            with contextlib.redirect_stderr(stderr),contextlib.redirect_stdout(io.StringIO()):
                self.run_logged([sys.executable,'-c','print("success")'],log)
            self.assertEqual(stderr.getvalue(),'')
            self.assertEqual(log.read_text(),'success\n')

    def test_log_tail_is_bounded_and_full_log_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'run.log'; stderr=io.StringIO()
            with contextlib.redirect_stderr(stderr),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.run_logged([sys.executable,'-c','print("x"*30000);print("FINAL ERROR");raise SystemExit(2)'],log)
            self.assertGreater(log.stat().st_size,30000)
            self.assertLess(len(stderr.getvalue()),17000)
            self.assertIn('FINAL ERROR',stderr.getvalue())

if __name__=='__main__': unittest.main()
