import unittest,os
from unittest.mock import patch
from test_organize_ari import Tests
from move_ari import execute
class Moves(Tests):
 def test_move(self):
  p,_=self.plan();d=self.root/'analyzed';execute(self.a,d,p['plan_sha256'],expected={298})
  self.assertTrue((d/'IMPORT_MOVE_VERIFIED').exists())
  for row in p['files']:self.assertFalse((self.a/row['archive_relative']).exists());self.assertTrue((d/row['destination']).exists())
 def test_resume_link_window(self):
  p,_=self.plan();d=self.root/'analyzed';real=os.link;calls=[]
  def interrupted(s,o,**kw):
   real(s,o,**kw);calls.append(s);raise OSError('interruption after link')
  with patch('move_ari.os.link',side_effect=interrupted):
   with self.assertRaises(OSError):execute(self.a,d,p['plan_sha256'],expected={298})
  self.assertTrue(calls[0].exists());execute(self.a,d,p['plan_sha256'],resume=True);self.assertFalse(calls[0].exists())
 def test_resume_after_unlink(self):
  p,_=self.plan();d=self.root/'analyzed';real=os.link;calls=[]
  def interrupted(s,o,**kw):
   if calls:raise OSError('next file failure')
   real(s,o,**kw);calls.append(s)
  with patch('move_ari.os.link',side_effect=interrupted):
   with self.assertRaises(OSError):execute(self.a,d,p['plan_sha256'],expected={298})
  self.assertFalse(calls[0].exists());execute(self.a,d,p['plan_sha256'],resume=True)
 def test_tamper_preflight(self):
  p,_=self.plan();(self.a/p['files'][0]['archive_relative']).write_bytes(b'changed');d=self.root/'analyzed'
  with self.assertRaisesRegex(ValueError,'Invalid file'):execute(self.a,d,p['plan_sha256'],expected={298})
  self.assertFalse(d.exists())
if __name__=='__main__':unittest.main()
