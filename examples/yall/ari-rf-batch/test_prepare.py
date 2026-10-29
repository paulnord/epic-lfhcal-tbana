#!/usr/bin/env python3
"""Run with yall-run importable; no ROOT, scheduler, or real data needed."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yall_run.syntax import load_yall_spec
spec=importlib.util.spec_from_file_location('prepare',Path(__file__).with_name('prepare.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class PreparationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='rf-test-');self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.raw=self.base/'raw';self.raw.mkdir()
        for pair in p.PAIRS:
            for r in pair[:2]: (self.raw/f'Run{r}.h2g').write_bytes(b'x')
        self.eic=self.base/'eic-shell';self.eic.touch();self.eic.chmod(0o755)
    def generate(self,mode='full'):
        dest=self.base/mode
        with contextlib.redirect_stdout(io.StringIO()): p.prepare(dest,self.raw,self.eic,mode,True)
        return load_yall_spec(dest/'Yallfile')
    def test_full(self):
        result=self.generate();tasks={t.name:t for t in result.tasks}
        self.assertEqual(len(tasks),145)
        self.assertEqual(len([n for n in tasks if n.startswith('convert-')]),26)
        self.assertEqual(len([n for n in tasks if n.startswith('pedestal-')]),13)
        self.assertEqual(len(tasks['summary'].parents),13)
        for n,t in tasks.items():
            if n.startswith('convert-'): self.assertEqual(t.parents,('build',))
        self.assertIn('305',str(tasks['transfer-305-306-1']))
        self.assertIn('ParamScan_2.csv',str(tasks['transfer-328-329-2']))
    def test_pilot(self): self.assertEqual(len(self.generate('pilot').tasks),13)
    def test_shared_pedestal_and_cross_column_union(self):
        with patch.object(p,'PAIRS',[(296,298,1),(296,300,1),(298,304,1)]): result=self.generate()
        names=[t.name for t in result.tasks]
        self.assertEqual(sorted(n for n in names if n.startswith('convert-')),['convert-296','convert-298','convert-300','convert-304'])
        self.assertEqual(sorted(n for n in names if n.startswith('pedestal-')),['pedestal-296','pedestal-298'])
        tasks={t.name:t for t in result.tasks}
        self.assertIn('pedestal-296',tasks['transfer-296-298-1'].parents)
        self.assertIn('pedestal-296',tasks['transfer-296-300-1'].parents)
    def test_refuses_overwrite(self):
        self.generate()
        with self.assertRaises(ValueError): self.generate()
    def test_missing_raw(self):
        (self.raw/'Run305.h2g').unlink()
        with self.assertRaisesRegex(ValueError,'Run305'): self.generate()

if __name__=='__main__': unittest.main()
