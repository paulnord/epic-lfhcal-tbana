#!/usr/bin/env python3
"""Run with yall-run importable; no ROOT, scheduler, or real data needed."""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import json
from yall_run.execution import archive_wrapper
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
    def test_archived_wrapper_is_self_contained(self):
        # Use Yall's actual relocation path, not the source wrapper path.
        self.eic.write_text('#!/bin/bash\nwhile read line; do eval "$line" || exit $?; done\n')
        result=self.generate('pilot')
        campaign=self.base/'campaign';campaign.mkdir()
        archived=archive_wrapper(result,campaign)
        command=[archived['path'],*archived['args'],sys.executable,'-c',
                 'import json,os,sys; print(json.dumps([os.environ.get("ARI_RF_BATCH_WORKER"),*sys.argv[1:]]))',
                 "apostrophe's value",r'literal\backslash']
        env=dict(os.environ,_CONDOR_JOB_AD='/test/condor-job-ad')
        run=subprocess.run(command,env=env,text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(run.stdout),['1',"apostrophe's value",r'literal\backslash'])
        failed=subprocess.run([archived['path'],*archived['args'],'/bin/false'],env=env)
        self.assertEqual(failed.returncode,1)
        env.pop('_CONDOR_JOB_AD')
        blocked=subprocess.run(command,env=env,capture_output=True)
        self.assertEqual(blocked.returncode,2)

    def test_symlink_invocation_provenance(self):
        alias=self.base/'alias-source';alias.symlink_to(p.REPO,target_is_directory=True)
        destination=self.base/'through-alias'
        subprocess.run([sys.executable,str(alias/'examples/yall/ari-rf-batch/prepare.py'),
                        '--destination',str(destination),'--raw',str(self.raw),
                        '--eic-shell',str(self.eic),'--mode','pilot','--accept-repo-scan-recipe'],
                       check=True,capture_output=True,text=True)
        metadata=json.loads((destination/'preparation.json').read_text())
        self.assertIn('examples/yall/ari-rf-batch/compare.py',metadata['input_sha256'])
        self.assertEqual(metadata['repo'],str(p.REPO))
    def test_provenance_failure_leaves_no_destination(self):
        with patch.object(p.subprocess,'check_output',side_effect=RuntimeError('provenance failed')):
            with self.assertRaises(RuntimeError): self.generate()
        self.assertFalse((self.base/'full').exists())

    def test_refuses_overwrite(self):
        self.generate()
        with self.assertRaises(ValueError): self.generate()
    def test_missing_raw(self):
        (self.raw/'Run305.h2g').unlink()
        with self.assertRaisesRegex(ValueError,'Run305'): self.generate()

if __name__=='__main__': unittest.main()
