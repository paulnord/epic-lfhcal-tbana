import contextlib, importlib.util, io, json, pathlib, sys, tempfile, unittest, subprocess
spec=importlib.util.spec_from_file_location('archive',pathlib.Path(__file__).with_name('archive_ari.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TestArchive(unittest.TestCase):
 def test_inventory_copy_and_refuse_overwrite(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td); source=root/'source';source.mkdir();parent=root/'pwg';parent.mkdir()
   (source/'calibratedHGCROC_Run_302.root').write_bytes(b'calibrated')
   (source/'plot.csv').write_text('run,value\n302,1\n')
   (source/'linked.csv').symlink_to(source/'plot.csv')
   (source/'calibratedHGCROC_Run_300.root').touch()
   subprocess.run(['git','init','-q',str(source)],check=True)
   subprocess.run(['git','-C',str(source),'add','.'],check=True)
   subprocess.run(['git','-C',str(source),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)
   (source/'preparation.json').write_text(json.dumps({'inputs':[{'run':302,'path':str(source/'calibratedHGCROC_Run_302.root')}]}))
   m.ROOTS=[str(source)];m.PARENT=parent;m.RAW=root/'raw'
   old=sys.argv
   try:
    sys.argv=['archive'];out=io.StringIO()
    with contextlib.redirect_stdout(out):m.main()
    self.assertEqual(list(parent.iterdir()),[])
    inventory=json.loads(out.getvalue());self.assertEqual(inventory['coverage']['calibrated_runs_present'],[302])
    dest=parent/'new'
    sys.argv=['archive','--copy','--destination',str(dest),'--quota-reviewed','--sources-quiescent']
    with contextlib.redirect_stdout(io.StringIO()):m.main()
    self.assertEqual((dest/'payload'/str(source/'plot.csv').lstrip('/')).read_text(),'run,value\n302,1\n')
    archived_link=dest/'payload'/str(source/'linked.csv').lstrip('/')
    self.assertFalse(pathlib.Path(archived_link.readlink()).is_absolute())
    self.assertEqual(archived_link.read_text(),'run,value\n302,1\n')
    bundle=dest/'metadata/source-000.bundle'
    subprocess.run(['git','-C',str(source),'bundle','verify',str(bundle)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    self.assertIn(m.sha(bundle)+'  metadata/source-000.bundle',(dest/'metadata/SHA256SUMS').read_text())
    self.assertTrue((dest/'COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED').exists())
    self.assertEqual(dest.stat().st_mode & 0o777,0o700)
    with self.assertRaisesRegex(RuntimeError,'already exists'):m.main()
   finally:sys.argv=old
 def test_source_mutation_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);source=root/'source';source.mkdir();parent=root/'pwg';parent.mkdir()
   f=source/'value.csv';f.write_text('original')
   m.ROOTS=[str(source)];m.PARENT=parent;m.RAW=root/'raw'
   oldargv=sys.argv;oldsha=m.sha;mutated=False
   def changing_sha(p):
    nonlocal mutated
    digest=oldsha(p)
    if p==f and not mutated:
     mutated=True;f.write_text('changed')
    return digest
   try:
    m.sha=changing_sha
    sys.argv=['archive','--copy','--destination',str(parent/'new'),'--quota-reviewed','--sources-quiescent']
    with self.assertRaisesRegex(RuntimeError,'mismatch or source changed'):m.main()
    self.assertFalse((parent/'new/COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED').exists())
   finally:m.sha=oldsha;sys.argv=oldargv
 def fixture(self,root):
  source=root/'source';source.mkdir();parent=root/'pwg';parent.mkdir()
  m.ROOTS=[str(source)];m.PARENT=parent;m.RAW=root/'raw'
  return source,parent
 def git_fixture(self,source):
  (source/'a.txt').write_text('source')
  subprocess.run(['git','init','-q',str(source)],check=True)
  subprocess.run(['git','-C',str(source),'add','.'],check=True)
  subprocess.run(['git','-C',str(source),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)
 def test_broken_parent_with_valid_module(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);source,parent=self.fixture(root)
   admin=source/'.git';admin.mkdir();(admin/'broken-parent-record').write_text('retain')
   module=source/'NewStructure/h2g_decode';module.mkdir(parents=True);self.git_fixture(module)
   import shutil
   module_admin=admin/'modules/NewStructure/h2g_decode';module_admin.parent.mkdir(parents=True)
   shutil.move(str(module/'.git'),str(module_admin))
   (module/'.git').write_text('gitdir: '+str(module_admin)+'\n')
   # Separate gitdir needs explicit worktree after relocation.
   subprocess.run(['git','--git-dir',str(module_admin),'config','core.worktree',str(module)],check=True)
   old=sys.argv
   try:
    dest=parent/'new';sys.argv=['archive','--copy','--destination',str(dest),'--quota-reviewed','--sources-quiescent']
    with contextlib.redirect_stdout(io.StringIO()):m.main()
    result=json.loads((dest/'metadata/verified-inventory.json').read_text())
    self.assertFalse(result['git'][str(source)]['valid_for_bundle'])
    self.assertTrue(result['git'][str(module)]['valid_for_bundle'])
    self.assertIn('bundle',result['git'][str(module)])
    self.assertEqual((dest/'payload'/str(admin/'broken-parent-record').lstrip('/')).read_text(),'retain')
   finally:sys.argv=old
 def test_bundle_failure_before_payload(self):
  with tempfile.TemporaryDirectory() as td:
   source,parent=self.fixture(pathlib.Path(td));self.git_fixture(source)
   oldargv=sys.argv;oldcmd=m.command
   def failure(args):
    if 'bundle' in args and 'create' in args:return {'command':args,'returncode':1,'stdout':'','stderr':'injected bundle failure'}
    return oldcmd(args)
   try:
    m.command=failure;dest=parent/'new'
    sys.argv=['archive','--copy','--destination',str(dest),'--quota-reviewed','--sources-quiescent']
    with self.assertRaisesRegex(RuntimeError,'Git bundle failed'):m.main()
    self.assertFalse((dest/'payload').exists())
   finally:m.command=oldcmd;sys.argv=oldargv
 def test_git_ref_mutation_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   source,parent=self.fixture(pathlib.Path(td));self.git_fixture(source)
   oldargv=sys.argv;oldsha=m.sha;changed=False
   def mutate(p):
    nonlocal changed
    digest=oldsha(p)
    if p==source/'a.txt' and not changed:
     changed=True;subprocess.run(['git','-C',str(source),'branch','new-ref'],check=True)
    return digest
   try:
    m.sha=mutate;dest=parent/'new'
    sys.argv=['archive','--copy','--destination',str(dest),'--quota-reviewed','--sources-quiescent']
    with self.assertRaisesRegex(RuntimeError,'Git source changed'):m.main()
    self.assertFalse((dest/'COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED').exists())
   finally:m.sha=oldsha;sys.argv=oldargv
 def test_unknown_quota_explicit_optin(self):
  with tempfile.TemporaryDirectory() as td:
   source,parent=self.fixture(pathlib.Path(td));(source/'a.csv').write_text('preserve')
   old=sys.argv
   try:
    dest=parent/'new';sys.argv=['archive','--copy','--destination',str(dest),'--sources-quiescent','--accept-unknown-quota']
    with contextlib.redirect_stdout(io.StringIO()):m.main()
    report=json.loads((dest/'metadata/verified-inventory.json').read_text())
    self.assertEqual(report['quota_status'],'unknown_explicitly_accepted')
    self.assertTrue((dest/'COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED').exists())
    sys.argv.append('--quota-reviewed')
    with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):m.main()
   finally:sys.argv=old
if __name__=='__main__':unittest.main()
