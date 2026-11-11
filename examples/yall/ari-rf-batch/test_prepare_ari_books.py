#!/usr/bin/env python3
"""Offline preparation contract: real git, fake inputs/Yall, no ROOT or submission."""
import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('prepare_ari_books.sh').resolve()
RUNS = [298,300,302,304,306,310,329,333,335,337,339,341,343,345,347,349,351,353,355,357,359,361,363]
RF = set(RUNS[:14])
HEADER = 'run,cell,status,has_peak,has_fwhm,peak_bin,left_bin,right_bin,amplitude,peak_time_ns,left_ns,right_ns,fwhm_ns,source'.split(',')

class BookPreparation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ari-books-prep-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.bin = self.base/'bin'; self.bin.mkdir()
        yall = self.bin/'yall-run'
        yall.write_text('#!/bin/sh\ncase "$1" in --version) echo 0.12.0a7;; validate|plan) echo "offline stub $1";; *) exit 99;; esac\n')
        yall.chmod(0o755)
        eic = self.bin/'eic-shell'; eic.write_text('#!/bin/sh\nexit 99\n'); eic.chmod(0o755)
        self.source = self.base/'repo'; self.source.mkdir()
        self.git('init', '-q')
        for name, content in {'NewStructure/CombineWaveformBooks.cc':'// WaveformScale::IsolatedLayer\n',
                              'NewStructure/Tests/test_waveform_books.cc':'// fixture\n',
                              'examples/yall/ari-rf-batch/worker.sh':'#!/bin/sh\nexit 99\n'}.items():
            p = self.source/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
        self.git('add', '.'); self.git('-c','user.name=Offline test','-c','user.email=offline@example.invalid','commit','-qm','fixture')
        self.commit = self.git('rev-parse','HEAD').strip()
        self.input_root = self.base/'inputs'; self.run302 = self.base/'run302'
        for run in RUNS:
            p = self.run302 if run == 302 else self.input_root/('rf' if run in RF else 'other')
            root = p/f'products/waveform/calibratedHGCROC_wave_Run_{run}_Hists.root'
            table = p/f'products/plots/waveform/Run{run}/WaveformGrid_Run{run}_Measurements.csv'
            root.parent.mkdir(parents=True, exist_ok=True); root.write_bytes(b'not ROOT; preflight only')
            table.parent.mkdir(parents=True, exist_ok=True)
            with table.open('w',newline='') as f:
                w=csv.writer(f);w.writerow(HEADER)
                for cell in range(64):w.writerow([run,cell]+['']*12)
        self.dest = self.base/'fresh'
        self.env = dict(os.environ, PATH=str(self.bin)+':'+os.environ['PATH'],
                        EIC_SHELL=str(eic), ARI_SOURCE_REPO=str(self.source),
                        ARI_SOURCE_COMMIT=self.commit, ARI_INPUT_ROOT=str(self.input_root),
                        ARI_RUN302_ROOT=str(self.run302))
        self.env.pop('ARI_RF_BATCH_WORKER',None);self.env.pop('_CONDOR_JOB_AD',None)

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.source),*args],text=True,stderr=subprocess.DEVNULL)

    def run_prepare(self,mode='isolated'):
        return subprocess.run(['/bin/bash',str(SCRIPT),str(self.dest),mode],env=self.env,text=True,capture_output=True)

    def test_explicit_commit_mode_fresh_clone_and_unchanged_inputs(self):
        before={p:p.read_bytes() for directory in (self.input_root,self.run302) for p in directory.rglob('*') if p.is_file()}
        result=self.run_prepare();self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads((self.dest/'preparation.json').read_text())
        self.assertEqual((data['commit'],data['scale']),(self.commit,'isolated'))
        self.assertEqual([r['run'] for r in data['inputs']],RUNS)
        self.assertEqual(subprocess.check_output(['git','-C',str(self.dest/'source'),'rev-parse','HEAD'],text=True).strip(),self.commit)
        self.assertNotEqual((self.dest/'source').resolve(),self.source.resolve())
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.assertIn('NO JOBS SUBMITTED',result.stdout)
        self.assertFalse((self.dest/'campaign-path.txt').exists())
        self.assertNotIn('HGCROCStudy',(self.dest/'run_books.sh').read_text())
        retry=self.run_prepare();self.assertNotEqual(retry.returncode,0)
        self.assertIn('fresh absolute destination',retry.stderr)

    def test_invalid_commit_rejected_before_creation(self):
        for commit in ('HEAD','abc','a'*39,'A'*40,'x'*40):
            self.env['ARI_SOURCE_COMMIT']=commit
            result=self.run_prepare();self.assertNotEqual(result.returncode,0)
            self.assertIn('40-hex',result.stderr);self.assertFalse(self.dest.exists())

    def test_isolated_requires_explicit_revision(self):
        del self.env['ARI_SOURCE_COMMIT']
        result=self.run_prepare();self.assertNotEqual(result.returncode,0)
        self.assertIn('explicit ARI_SOURCE_COMMIT',result.stderr);self.assertFalse(self.dest.exists())

    def test_selected_revision_must_support_isolated(self):
        (self.source/'NewStructure/CombineWaveformBooks.cc').write_text('// old implementation\n')
        self.git('add','.');self.git('-c','user.name=Offline test','-c','user.email=offline@example.invalid','commit','-qm','old fixture')
        self.env['ARI_SOURCE_COMMIT']=self.git('rev-parse','HEAD').strip()
        result=self.run_prepare();self.assertNotEqual(result.returncode,0)
        self.assertIn('lacks isolated',result.stderr)
        self.assertFalse((self.dest/'submit_books.sh').exists())

    def test_legacy_mode_supported_with_explicit_revision(self):
        result=self.run_prepare('layer');self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads((self.dest/'preparation.json').read_text())['scale'],'layer')

if __name__ == '__main__':unittest.main()
