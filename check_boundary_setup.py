#!/usr/bin/env python3
"""Integration fixture for isolation, full DAG, reference joins and diagnostics.
Uses real archived source/recipes, synthetic event placeholders (never fitted).
"""
import csv,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));import prepare_boundary_fullchains as prep

def main():
 archive=next(p for p in (HERE/'control-study-inputs/fit-range-controls-20261002/campaigns',HERE.parent/'control-study-inputs/fit-range-controls-20261002/campaigns') if p.is_dir());root=HERE/'boundary-fixture'
 if root.exists():shutil.rmtree(root)
 root.mkdir();repo=root/'repo';repo.mkdir();work=root/'work';work.mkdir();relocated=root/'archive';relocated.mkdir()
 for name,path in prep.PAYLOADS.items():
  dest=repo/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(HERE/name if (HERE/name).is_file() else HERE/path,dest)
 subprocess.run(['git','init','-q',str(repo)],check=True);subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],check=True)
 shell=root/'eic-shell';shell.write_text('#!/bin/sh\nexec "$@"\n');shell.chmod(0o755)
 early=prep.load(archive/prep.EARLY/'manifest.json');remaining=prep.load(archive/prep.REMAINING/'manifest.json');specs={**early['specs'],**remaining['specs']}
 originals={c:prep.EARLY if c in ('b2','e1','e3') else prep.RECOVERY if c=='d1' else prep.REMAINING for c in prep.CODES}
 all_inputs={}
 for c in prep.CODES:
  data=root/f'rawHGCROC_wPed_wBC_Muon_{specs[c]["fullset"]}.root';data.write_bytes(b'fixture pre-MIP input; never run as ROOT');all_inputs[c]=dict(mode='transfer',files=dict(transfer=dict(path=str(data.resolve()),size=data.stat().st_size,mtime_ns=data.stat().st_mtime_ns)))
 source_hashes={}
 for model in ('legacy','adaptive'):
  source_hashes[model]={}
  src=archive/prep.EARLY/'sources'/model
  for p in src.rglob('*'):
   if p.is_file():source_hashes[model][str(p.relative_to(src))]=prep.sha(p)
 for name in (prep.EARLY,prep.REMAINING,prep.RECOVERY):
  target=work/name;target.mkdir();manifest=dict(early,specs=specs if name==prep.RECOVERY else early['specs'] if name==prep.EARLY else remaining['specs'],inputs=all_inputs,eic_shell=str(shell.resolve()),eic_shell_sha256=prep.sha(shell));prep.dump(target/'manifest.json',manifest);prep.dump(target/'source-hashes.json',source_hashes);(target/'run-in-eic-shell.sh').write_text('#!/bin/sh\nexec "$@"\n');(target/'run-in-eic-shell.sh').chmod(0o755)
  shutil.copy2(archive/prep.EARLY/'adaptive_fulltests.py',target/'adaptive_fulltests.py')
  for model in ('legacy','adaptive'):prep.dump(target/f'build-{model}.json',dict(root_version='6.40.04'));shutil.copytree(archive/prep.EARLY/'sources'/model,target/'sources'/model)
 for c in prep.CODES:
  ready=work/originals[c]/'inputs'/c/'ready.json';ready.parent.mkdir(parents=True)
  info=all_inputs[c]['files']['transfer'];prep.dump(ready,dict(transfer=dict(info,sha256=prep.sha(info['path'])),trees={'events':1234},boundary='before initial MIP calibration',mode='transfer'))
  for model in ('legacy','adaptive'):
   for stage in ('mip','select')+tuple('refine'+str(n) for n in range(1,9 if c=='b2' else 6)):
    parent=work/(prep.EXTENSION if c=='b2' and stage in ('refine6','refine7','refine8') else originals[c]);d=parent/model/c/stage;d.mkdir(parents=True)
    record=dict(model=model,dataset=c,stage=stage,event_trees={'events':1234},execution=dict(returncode=0),saved_fits=1,available_calibrations=2,total_trigger_entries=1000.,mean_scale_h=50.)
    prep.dump(d/'stage.json',record)
    if stage=='select':(d/f'rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_{specs[c]["fullset"]}.root').write_bytes(f'original selection {model} {c}; distinct fixture bytes'.encode())
    if stage!='select':(d/'cells.csv').write_text('cell_id,bc,scale_h,fwhm_h,fit_saved,entries,histogram_sha256\n67,3,50,20,True,1000,reference\n68,3,40,20,False,20,second\n')
 # Missing original B1; archive contains a same-size decoy and a renamed-directory exact copy.
 old=Path(all_inputs['b1']['files']['transfer']['path']);good=relocated/'moved'/'transfer'/old.name;good.parent.mkdir(parents=True);old.rename(good)
 bad=relocated/'fullset-b1-repro'/'transfer'/old.name;bad.parent.mkdir(parents=True);bad.write_bytes(b'x'*good.stat().st_size)
 # A selected-event file must never be discovered as a pre-MIP candidate.
 (bad.parent/('selected_'+old.name)).write_bytes(good.read_bytes())
 original_hashes={str(p):prep.sha(p) for p in work.rglob('*') if p.is_file()}
 out=root/'prepared';cmd=[sys.executable,str(HERE/'prepare_boundary_fullchains.py'),'--repo',str(repo),'--ref','HEAD','--work',str(work),'--archive',str(relocated),'--out',str(out)]
 missing=[Path(all_inputs[c]['files']['transfer']['path']) for c in ('e1','e2')]
 for p in missing:p.rename(p.with_suffix('.held'))
 failure=subprocess.run(cmd,capture_output=True,text=True)
 assert failure.returncode!=0 and 'E1: No candidate' in failure.stderr and 'E2: No candidate' in failure.stderr,failure.stderr
 assert not out.exists(),'Failed preflight left a partial campaign'
 for p in missing:p.with_suffix('.held').rename(p)
 subprocess.run(cmd,check=True)
 assert all(prep.sha(Path(p))==h for p,h in original_hashes.items()),'Reference campaign mutated'
 assert subprocess.run(cmd,capture_output=True).returncode!=0,'Existing output overwrite allowed'
 yall=out/'Yallfile';subprocess.run([sys.executable,'-m','yall_run.cli','validate',str(yall)],check=True)
 worker=prep.module(out/'boundary_fullchains.py','tested_worker');b=worker.base_module(out)
 # Exercise the real hash-verification worker; stub only the build/ROOT dependencies.
 manifest=prep.load(out/'manifest.json');incoming=manifest['inputs']['b1']
 assert [i['path'] for i in incoming['transfer_candidates']]==[str(bad.resolve()),str(good.resolve())]
 with patch.object(b,'check_sources'),patch.object(b,'environment'),patch.object(b,'check_root',return_value={'events':1234}) as root_check:
  worker.common_input(b,out,'b1')
  verified=prep.load(out/'inputs/b1/ready.json');assert verified['transfer']['path']==str(good.resolve())
  assert verified['transfer']['sha256']==incoming['expected_transfer']['sha256']
  root_check.assert_called_once_with(good.resolve(),events=True)
  # Same-size wrong bytes alone must not emit a readiness marker or enter ROOT.
  failed=root/'input-failure';failed.mkdir();changed=json.loads(json.dumps(manifest));changed['inputs']['b1']['transfer_candidates']=[incoming['transfer_candidates'][0]];prep.dump(failed/'manifest.json',changed)
  root_check.reset_mock()
  try:worker.common_input(b,failed,'b1')
  except ValueError as e:assert 'No byte-identical original' in str(e)
  else:raise AssertionError('Wrong same-size input accepted')
  assert not (failed/'inputs/b1/ready.json').exists();root_check.assert_not_called()
  # Changed size/mtime since preparation is still an error, even on a moved copy.
  changed['inputs']['b1']['transfer_candidates']=[dict(incoming['transfer_candidates'][1],mtime_ns=0)];prep.dump(failed/'manifest.json',changed)
  try:worker.common_input(b,failed,'b1')
  except ValueError as e:assert 'Input changed after preparation' in str(e)
  else:raise AssertionError('Changed input metadata accepted')
  assert not (failed/'inputs/b1/ready.json').exists()
 # Original hash is mandatory, rather than inferred from a newly discovered copy.
 record=prep.load(work/originals['b1']/'inputs/b1/ready.json');del record['transfer']['sha256'];unhashed=root/'unhashed.json';prep.dump(unhashed,record)
 try:prep.resolve_input(b,'b1',all_inputs['b1'],unhashed,{good.name:[good]},[relocated])
 except ValueError as e:assert 'Missing valid original transfer SHA-256' in str(e)
 else:raise AssertionError('Unverifiable original accepted')
 assert all(prep.sha(Path(p))==h for p,h in original_hashes.items()),'Input verification mutated original records'
 # Create controlled post-run reports; assert joins, stage coverage and known deltas.
 for c in prep.CODES:
  for model in b.MODELS:
   for stage in worker.stages(c):
    d=b.paths(out,model,c,stage)['directory'];d.mkdir(parents=True,exist_ok=True);ref=out/'references'/model/c/stage;record=prep.load(ref/'stage.json');record.update(carried_forward=1,range_counts={'raised':1});prep.dump(d/'stage.json',record)
    if stage!='select':(d/'cells.csv').write_text('cell_id,bc,scale_h,fwhm_h,fit_saved,entries,histogram_sha256,carried_forward,range_status\n67,3,49,19,True,1001,new,False,raised\n68,3,40,20,False,20,second,True,no_prominent_peak\n')
  worker.compare(b,out,c)
 worker.summary(b,out)
 stages=list(csv.DictReader((out/'all-stage-statistics.csv').open()));assert len(stages)==348,len(stages)
 rows=list(csv.DictReader((out/'all-cell-boundary-comparisons.csv').open()));assert len(rows)==348,len(rows)
 assert all(abs(float(r['relative_change_scale_h'])+.02)<1e-12 for r in rows if r['cell_id']=='67')
 assert any(r['dataset']=='b2' and r['stage']=='refine8' for r in rows)
 assert not any(r['dataset']!='b2' and r['stage'] in ('refine6','refine7','refine8') for r in rows)
 print('PASS: missing-input aggregation; relocated exact input accepted; same-size wrong input, metadata changes and missing original hash rejected; no ready marker on failure.')
 print('PASS: 233-task DAG; isolated snapshots; original references unchanged; R8 only B2; four-way joins and H deltas verified.')
 # Resume must work even when every pre-MIP input and original ready record is gone.
 held=[]
 for p in [Path(i['files']['transfer']['path']) for i in all_inputs.values()]+[good,bad]+[work/originals[c]/'inputs'/c/'ready.json' for c in prep.CODES]:
  if p.exists():p.rename(p.with_suffix(p.suffix+'.held'));held.append(p)
 resumed=root/'resumed';resume_cmd=cmd[:-1]+[str(resumed),'--reuse-selection']
 absent=[b.paths(work/originals[c],model,c,'select')['root'] for c,model in [('e1','legacy'),('d1','adaptive')]]
 for p in absent:p.rename(p.with_suffix('.held'))
 failure=subprocess.run(resume_cmd,capture_output=True,text=True)
 assert failure.returncode!=0 and 'E1 legacy:' in failure.stderr and 'D1 adaptive:' in failure.stderr,failure.stderr
 assert not resumed.exists(),'Failed selection preflight left a partial campaign'
 for p in absent:p.with_suffix('.held').rename(p)
 subprocess.run(resume_cmd,check=True)
 for p in held:p.with_suffix(p.suffix+'.held').rename(p)
 subprocess.run([sys.executable,'-m','yall_run.cli','validate',str(resumed/'Yallfile')],check=True)
 yall=(resumed/'Yallfile').read_text();tasks=[line for line in yall.splitlines() if line and not line.startswith((' ','%')) and ':' in line]
 assert len(tasks)==191,len(tasks)
 assert not any(line.startswith(('mip-','select-','input-')) for line in tasks)
 assert 'refine1-legacy-b1: selection-legacy-b1' in tasks
 assert 'refine1-adaptive-b1: selection-adaptive-b1' in tasks
 assert 'refine8-adaptive-b2: refine7-adaptive-b2' in tasks
 rw=prep.module(resumed/'boundary_fullchains.py','resumed_worker');rb=rw.base_module(resumed);rm=prep.load(resumed/'manifest.json')
 assert rm['reuse_selection'] and not rm['inputs']
 # Failed ROOT verification leaves neither a published snapshot nor ready marker.
 with patch.object(rb,'check_sources'),patch.object(rb,'environment'),patch.object(rb,'check_root',return_value={'events':999}):
  try:rw.snapshot_selection(rb,resumed,'legacy','b1')
  except ValueError as e:assert 'tree counts differ' in str(e)
  else:raise AssertionError('Mismatched selection event counts accepted')
 p=rb.paths(resumed,'legacy','b1','select')['root']
 assert not p.exists() and not p.with_suffix('.root.partial').exists() and not rw.selection_ready(resumed,'legacy','b1').exists()
 # A source modified after preparation must be rejected before copying.
 original=Path(rm['selection_inputs']['b1']['legacy']['file']['path']);stat=original.stat();os.utime(original,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000))
 with patch.object(rb,'check_sources'),patch.object(rb,'environment'):
  try:rw.snapshot_selection(rb,resumed,'legacy','b1')
  except ValueError as e:assert 'Input changed after preparation' in str(e)
  else:raise AssertionError('Changed original selection accepted')
 os.utime(original,ns=(stat.st_atime_ns,stat.st_mtime_ns))
 with patch.object(rb,'check_sources'),patch.object(rb,'environment'),patch.object(rb,'check_root',return_value={'events':1234}):
  for c in prep.CODES:
   for model in rb.MODELS:
    rw.snapshot_selection(rb,resumed,model,c);rw.check_selection(rb,resumed,model,c)
    selected=rb.paths(resumed,model,c,'select')['root'];record=prep.load(rw.selection_ready(resumed,model,c));original=Path(rm['selection_inputs'][c][model]['file']['path'])
    assert selected.read_bytes()==original.read_bytes()==f'original selection {model} {c}; distinct fixture bytes'.encode()
    assert prep.sha(selected)==record['selected']['sha256']==record['original_selected']['sha256']
    command=rb.stage_command(resumed,model,c,'refine1',Path('/test/DataPrep'))
    assert str(command[command.index('-i')+1])==str(selected) and '-k' not in command
    command2=rb.stage_command(resumed,model,c,'refine2',Path('/test/DataPrep'))
    assert command2[command2.index('-k')+1]==rb.paths(resumed,model,c,'refine1')['calib']
  try:rw.snapshot_selection(rb,resumed,'legacy','b1')
  except ValueError as e:assert 'Preserving existing selection snapshot' in str(e)
  else:raise AssertionError('Existing selected events overwritten')
 # Cross-method ready records cannot silently redirect a refinement.
 ready_path=rw.selection_ready(resumed,'legacy','b1');saved=prep.load(ready_path);wrong=dict(saved,model='adaptive');prep.dump(ready_path,wrong)
 try:rw.check_selection(rb,resumed,'legacy','b1')
 except ValueError as e:assert 'different method/dataset' in str(e)
 else:raise AssertionError('Wrong method selection accepted')
 prep.dump(ready_path,saved)
 for c in prep.CODES:
  for model in rb.MODELS:
   for stage in ('mip','select'):
    initial=prep.load(rb.paths(resumed,model,c,stage)['summary']);assert initial['execution_origin']=='reused_original' and 'execution' not in initial
   for stage in rw.stages(c)[2:]:
    d=rb.paths(resumed,model,c,stage)['directory'];d.mkdir(parents=True);ref=resumed/'references'/model/c/stage;record=prep.load(ref/'stage.json');record.update(carried_forward=1,range_counts={'raised':1},execution_origin='new_run');prep.dump(d/'stage.json',record)
    (d/'cells.csv').write_text('cell_id,bc,scale_h,fwhm_h,fit_saved,entries,histogram_sha256,carried_forward,range_status\n67,3,49,19,True,1001,new,False,raised\n68,3,40,20,False,20,second,True,no_prominent_peak\n')
  rw.compare(rb,resumed,c)
 rw.summary(rb,resumed)
 rows=list(csv.DictReader((resumed/'all-cell-boundary-comparisons.csv').open()));assert len(rows)==348
 assert all(float(r['relative_change_scale_h'])==0 and r['execution_origin']=='reused_original' for r in rows if r['stage']=='mip')
 assert all(abs(float(r['relative_change_scale_h'])+.02)<1e-12 and r['execution_origin']=='new_run' for r in rows if r['cell_id']=='67' and r['stage']!='mip')
 rows=list(csv.DictReader((resumed/'all-stage-statistics.csv').open()));assert len(rows)==348
 assert sum(r['execution_origin']=='reused_original' for r in rows)==28
 assert all(r['wall_s']=='?' for r in rows if r['execution_origin']=='reused_original')
 assert all(prep.sha(Path(p))==h for p,h in original_hashes.items()),'Resume setup modified original campaign data'
 print('PASS: 191-task resume DAG; no pre-MIP data required; all 28 method-specific copies and hashes verified; wrong counts/metadata/methods rejected; reused stages labeled; only new refinements change H.')
if __name__=='__main__':main()
