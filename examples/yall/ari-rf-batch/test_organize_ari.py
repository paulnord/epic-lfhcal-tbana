import hashlib,json,tempfile,unittest
from pathlib import Path
import organize_ari as m
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.a=self.root/'archive';self.a.mkdir();(self.a/'metadata').mkdir();(self.a/'COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED').write_text('verified');self.files={}
  for rel in ('calibrated/calibratedHGCROC_Run_298.root','waveform/calibratedHGCROC_wave_Run_298_Hists.root','plots/waveform/Run298/WaveformGrid_Run298_Measurements.csv'):
   self.add(m.ROOTS['rf']+rel)
  self.save()
 def tearDown(self):self.tmp.cleanup()
 def add(self,original,body=b'fixture'):
  rel='payload/'+original.lstrip('/');p=self.a/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
  self.files[original]={'archive_relative':rel,'sha256':hashlib.sha256(body).hexdigest(),'fingerprint':[0,0,0,len(body),0,0]}
 def save(self): (self.a/'metadata/verified-inventory.json').write_text(json.dumps({'files':self.files}))
 def plan(self):return m.make_plan(self.a,{298})
 def test_dryrun_no_mutation(self):
  before=sorted(str(p) for p in self.root.rglob('*'));plan,_=self.plan();self.assertEqual(len(plan['files']),3);self.assertEqual(before,sorted(str(p) for p in self.root.rglob('*')))
 def test_copy(self):
  plan,doc=self.plan();d=self.root/'analyzed';m.copy_plan(plan,doc,d,plan['plan_sha256'],True);self.assertTrue((d/'IMPORT_BYTE_VERIFIED').is_file());self.assertFalse((d/'INCOMPLETE').exists());self.assertEqual((d/'calibrated/calibratedHGCROC_Run_298.root').read_bytes(),b'fixture')
 def test_tamper(self):
  plan,doc=self.plan();p=self.a/plan['files'][0]['archive_relative'];p.write_bytes(b'changed');d=self.root/'analyzed'
  with self.assertRaisesRegex(ValueError,'Checksum mismatch'):m.copy_plan(plan,doc,d,plan['plan_sha256'],True)
  self.assertTrue((d/'INCOMPLETE').exists());self.assertFalse((d/'IMPORT_BYTE_VERIFIED').exists())
 def test_collision(self):
  self.add(m.ROOTS['other']+'calibrated/calibratedHGCROC_Run_298.root',b'different');self.save()
  with self.assertRaisesRegex(ValueError,'Conflicting destination'):self.plan()
 def test_identical_duplicate(self):
  self.add(m.ROOTS['other']+'calibrated/calibratedHGCROC_Run_298.root');self.save();self.assertEqual(self.plan()[0]['identical_duplicates'],1)
 def test_existing_destination(self):
  plan,doc=self.plan();d=self.root/'analyzed';d.mkdir()
  with self.assertRaisesRegex(ValueError,'already exists'):m.copy_plan(plan,doc,d,plan['plan_sha256'],True)
 def test_traversal(self):
  first=next(iter(self.files));self.files[first]['archive_relative']='../escape';self.save()
  with self.assertRaisesRegex(ValueError,'Unsafe relative path'):self.plan()
 def test_symlink(self):
  first=next(iter(self.files));p=self.a/self.files[first]['archive_relative'];p.unlink();p.symlink_to(self.a/'COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED')
  with self.assertRaisesRegex(ValueError,'symlink'):self.plan()
 def test_missing_run(self):
  with self.assertRaisesRegex(ValueError,'Missing calibrated'):m.make_plan(self.a,{298,331})
 def test_wrong_plan(self):
  plan,doc=self.plan()
  with self.assertRaisesRegex(ValueError,'hash mismatch'):m.copy_plan(plan,doc,self.root/'analyzed','bad',True)
 def test_excluded_partial_and_old302(self):
  self.assertIsNone(m.target_for(m.PREFIX+'ari-rebuild-eX4Mld/interrupted-products-abc/rf/products/calibrated/calibratedHGCROC_Run_298.root'))
  self.assertIsNone(m.target_for(m.ROOTS['run302']+'waveform/calibratedHGCROC_wave_Run_302_Hists.root'))
  self.assertEqual(m.target_for(m.ROOTS['run302_annotations']+'waveform/calibratedHGCROC_wave_Run_302_Hists.root')[1],'waveform/calibratedHGCROC_wave_Run_302_Hists.root')
if __name__=='__main__':unittest.main()
