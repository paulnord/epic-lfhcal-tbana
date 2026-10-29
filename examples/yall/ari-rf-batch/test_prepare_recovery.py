#!/usr/bin/env python3
"""Real yall parser/campaign schema tests; no scheduler or ROOT needed."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yall_run.syntax import load_yall_spec
from yall_run.campaign import create_campaign

spec=importlib.util.spec_from_file_location('recovery',Path(__file__).with_name('prepare_recovery.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='rf-recovery-test-');self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);raw=self.base/'raw';raw.mkdir()
        for pair in r.PAIRS:
            for n in pair[:2]: (raw/f'Run{n}.h2g').write_bytes(b'raw')
        self.eic=self.base/'eic-shell';self.eic.touch();self.eic.chmod(0o755)
        self.old=self.base/'old';self.dest=self.base/'recovery'
        with contextlib.redirect_stdout(io.StringIO()):
            r._p.prepare(self.old,raw,self.eic,'full',True)
            self.campaign=create_campaign(load_yall_spec(self.old/'Yallfile'),self.base/'campaigns')
        self.manifest=r.read_json(self.campaign/'campaign.json')
        for ped,run,scan in r.PAIRS:
            name=f'transfer-{ped}-{run}-{scan}'
            path=self.old/f'products/transfer/rawHGCROC_wPed_wBC_{run}.root'
            path.write_bytes(b'placeholderROOT')
            stat=path.stat()
            state={'state':'completed','attempts':1,'last_returncode':0}
            (self.campaign/'state'/f'{name}.json').write_text(json.dumps(state))
            ad=self.campaign/f'{name}_attempt_001';ad.mkdir()
            record={'task':name,'attempt':1,'state':'completed','returncode':0,'command_returncode':0,'command':self.manifest['tasks'][name]['command'],'outputs':[{'role':'root','path':str(path),'exists':True,'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}]}
            (ad/'attempt.json').write_text(json.dumps(record))
        self.before={str(p):p.read_bytes() for p in self.old.rglob('*') if p.is_file()}
    def generate(self):
        with contextlib.redirect_stdout(io.StringIO()):r.prepare(self.dest,self.old,self.campaign,self.eic)
        return load_yall_spec(self.dest/'Yallfile')
    def test_recovery_graph_and_untouched_old_workspace(self):
        tasks={t.name:t for t in self.generate().tasks}
        self.assertEqual(len(tasks),93)
        self.assertEqual(len(tasks['summary'].parents),13)
        for ped,run,scan in r.PAIRS:
            t=tasks[f'mip-{ped}-{run}-{scan}']
            self.assertEqual(t.parents,('build',))
            self.assertIn(str(self.old/f'products/transfer/rawHGCROC_wPed_wBC_{run}.root'),str(t.inputs))
        self.assertIsInstance(tasks['build'].command,str)
        self.assertIn(' && python3 ',tasks['build'].command)
        self.assertIn('--verify-root',tasks['build'].command)
        self.assertEqual(self.before,{str(p):p.read_bytes() for p in self.old.rglob('*') if p.is_file()})
        data=r.read_json(self.dest/'recovery.json')
        self.assertEqual(len(data['transfers']),13)
        self.assertEqual(data['previous_source_commit'],r.read_json(self.old/'preparation.json')['commit'])
    def test_failed_transfer_refused(self):
        p=self.campaign/'state/transfer-296-298-1.json'
        d=r.read_json(p);d['state']='failed';p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'not completed'):self.generate()
        self.assertFalse(self.dest.exists())
    def test_changed_transfer_refused(self):
        (self.old/'products/transfer/rawHGCROC_wPed_wBC_298.root').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):self.generate()
        self.assertFalse(self.dest.exists())
    def test_pair_mismatch_refused(self):
        p=self.old/'preparation.json';d=r.read_json(p);d['pairs'][0][0]=297;p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'exact full 13'):self.generate()
    def test_wrong_task_input_refused(self):
        p=self.campaign/'campaign.json';d=r.read_json(p)
        d['tasks']['transfer-296-298-1']['inputs'][0]['path']='/wrong/pedestal.root'
        p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'input mismatch'):self.generate()
    def test_archived_recipe_hash_refused(self):
        p=self.campaign/'Yallfile';p.write_text(p.read_text()+'\n# changed\n')
        with self.assertRaisesRegex(ValueError,'hash'):self.generate()
    def test_existing_destination_refused(self):
        self.dest.mkdir()
        with self.assertRaisesRegex(ValueError,'Destination exists'):self.generate()
    def test_provenance_failure_is_atomic(self):
        with patch.object(r.subprocess,'check_output',side_effect=RuntimeError('git failed')):
            with self.assertRaises(RuntimeError):self.generate()
        self.assertFalse(self.dest.exists())
    def test_command_mismatch_refused(self):
        p=self.campaign/'transfer-296-298-1_attempt_001/attempt.json'
        d=r.read_json(p);d['command']=['false'];p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'command differs'):self.generate()
    def test_destination_inside_old_workspace_refused(self):
        self.dest=self.old/'recovery'
        with self.assertRaisesRegex(ValueError,'outside'):self.generate()
    def test_root_check_refuses_login_host(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(ValueError,'Condor worker'):r.verify_root(self.base/'missing')

@unittest.skipUnless(importlib.util.find_spec('ROOT'), 'PyROOT unavailable')
class RootStructureTest(unittest.TestCase):
    def setUp(self):
        import ROOT
        from array import array
        self.tmp=tempfile.TemporaryDirectory(prefix='rf-root-test-');self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.path=self.base/'transfer.root'
        f=ROOT.TFile(str(self.path),'RECREATE')
        value=array('i',[1])
        for name,branch in [('Setup','setup'),('Data','event'),('Calib','calib')]:
            tree=ROOT.TTree(name,name);tree.Branch(branch,value,branch+'/I');tree.Fill();tree.Write()
        f.Close()
        self.metadata=self.base/'recovery.json'
        self.write_metadata()
    def write_metadata(self):
        stat=self.path.stat()
        self.metadata.write_text(json.dumps({'transfers':[{'path':str(self.path),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}]}))
    def verify(self):
        with patch.dict('os.environ',{'ARI_RF_BATCH_WORKER':'1'}),contextlib.redirect_stdout(io.StringIO()):
            r.verify_root(self.metadata)
    def test_real_root_with_expected_trees_passes(self):self.verify()
    def test_real_root_missing_calib_refused(self):
        import ROOT
        f=ROOT.TFile(str(self.path),'UPDATE');f.Delete('Calib;*');f.Close();self.write_metadata()
        with self.assertRaisesRegex(ValueError,'Calib'):self.verify()
    def test_changed_file_after_preparation_refused(self):
        self.path.write_bytes(b'not a root file')
        with self.assertRaisesRegex(ValueError,'changed'):self.verify()
    def test_corrupt_root_refused(self):
        self.path.write_bytes(b'not a root file');self.write_metadata()
        with self.assertRaises((ValueError,OSError)):self.verify()

if __name__=='__main__':unittest.main()
