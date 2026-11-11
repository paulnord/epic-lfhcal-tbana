#!/usr/bin/env python3
"""Offline native-yall tests; no scheduler, ROOT or detector data required."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from yall_run.model import load_spec
spec=importlib.util.spec_from_file_location('other',Path(__file__).with_name('prepare_other_scans.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class OtherScansTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='other-scans-');self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.raw=self.base/'raw';self.raw.mkdir()
        for ped,run,_ in p.PAIRS:
            for n in (ped,run): (self.raw/f'Run{n}.h2g').write_bytes(b'x')
        self.eic=self.base/'eic-shell';self.eic.touch();self.eic.chmod(0o755)
        self.dest=self.base/'work'
    def generate(self,accept=True):
        with contextlib.redirect_stdout(io.StringIO()):
            p.prepare(self.dest,self.raw,self.eic,accept,self.base/'previous-recovery')
        return load_spec(self.dest/'Yallfile')
    def test_graph(self):
        spec=self.generate();tasks={t.name:t for t in spec.tasks}
        self.assertEqual(len(tasks),100)
        self.assertNotIn('summary',tasks)
        for prefix,count in [('convert-',18),('pedestal-',9),('transfer-',9),('waveform-',9)]:
            self.assertEqual(sum(n.startswith(prefix) for n in tasks),count)
        for ped,run,_ in p.PAIRS:
            transfer=tasks[f'transfer-{ped}-{run}-2']
            self.assertIn('ParamScan_2.csv',str(transfer))
            self.assertEqual(tasks[f'convert-{run}'].parents,('build',))
            self.assertIn(f'calibrate-{ped}-{run}-2',tasks[f'waveform-{ped}-{run}-2'].parents)
        self.assertEqual(sum(n=='waveform-354-355-2' for n in tasks),1)
        self.assertNotIn('convert-298',tasks)
    def test_scan_metadata(self):
        self.generate();d=json.loads((self.dest/'preparation.json').read_text())
        self.assertEqual(len(d['pairs']),9)
        m=d['scan_manifest'];self.assertIn(355,m['scans']['CF']['runs']);self.assertIn(355,m['scans']['CFComp']['runs'])
        self.assertEqual(m['run_settings']['359']['CFComp'],15)
        self.assertEqual(m['run_settings']['363'],m['run_settings']['355'])
        self.assertIn('baseline_reference_only',m)
        self.assertIn('examples/yall/ari-rf-batch/prepare_other_scans.py',d['input_sha256'])
    def test_missing_raw_atomic(self):
        (self.raw/'Run363.h2g').unlink()
        with self.assertRaisesRegex(ValueError,'Run363'):self.generate()
        self.assertFalse(self.dest.exists())
    def test_acknowledgement(self):
        with self.assertRaises(ValueError):self.generate(False)
        self.assertFalse(self.dest.exists())
    def test_no_overwrite(self):
        self.generate()
        with self.assertRaisesRegex(ValueError,'already exists'):self.generate()

if __name__=='__main__':unittest.main()
