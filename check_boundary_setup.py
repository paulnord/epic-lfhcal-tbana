#!/usr/bin/env python3
"""Integration fixture for isolation, full DAG, reference joins and diagnostics.
Uses real archived source/recipes, synthetic event placeholders (never fitted).
"""
import csv,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));import prepare_boundary_fullchains as prep

def main():
 archive=next(p for p in (HERE/'control-study-inputs/fit-range-controls-20261002/campaigns',HERE.parent/'control-study-inputs/fit-range-controls-20261002/campaigns') if p.is_dir());root=HERE/'boundary-fixture'
 if root.exists():shutil.rmtree(root)
 root.mkdir();repo=root/'repo';repo.mkdir();work=root/'work';work.mkdir()
 for name,path in prep.PAYLOADS.items():
  dest=repo/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(HERE/name if (HERE/name).is_file() else HERE/path,dest)
 subprocess.run(['git','init','-q',str(repo)],check=True);subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],check=True)
 shell=root/'eic-shell';shell.write_text('#!/bin/sh\nexec "$@"\n');shell.chmod(0o755)
 early=prep.load(archive/prep.EARLY/'manifest.json');remaining=prep.load(archive/prep.REMAINING/'manifest.json');specs={**early['specs'],**remaining['specs']}
 originals={c:prep.EARLY if c in ('b2','e1','e3') else prep.RECOVERY if c=='d1' else prep.REMAINING for c in prep.CODES}
 all_inputs={}
 for c in prep.CODES:
  data=root/f'{c}.root';data.write_bytes(b'fixture pre-MIP input; never run as ROOT');all_inputs[c]=dict(mode='transfer',files=dict(transfer=dict(path=str(data.resolve()),size=data.stat().st_size,mtime_ns=data.stat().st_mtime_ns)))
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
  for model in ('legacy','adaptive'):
   for stage in ('mip','select')+tuple('refine'+str(n) for n in range(1,9 if c=='b2' else 6)):
    parent=work/(prep.EXTENSION if c=='b2' and stage in ('refine6','refine7','refine8') else originals[c]);d=parent/model/c/stage;d.mkdir(parents=True)
    record=dict(execution=dict(returncode=0),saved_fits=1,available_calibrations=2,total_trigger_entries=1000.,mean_scale_h=50.)
    prep.dump(d/'stage.json',record)
    if stage!='select':(d/'cells.csv').write_text('cell_id,bc,scale_h,fwhm_h,fit_saved,entries,histogram_sha256\n67,3,50,20,True,1000,reference\n68,3,40,20,False,20,second\n')
 original_hashes={str(p):prep.sha(p) for p in work.rglob('*') if p.is_file()}
 out=root/'prepared';cmd=[sys.executable,str(HERE/'prepare_boundary_fullchains.py'),'--repo',str(repo),'--ref','HEAD','--work',str(work),'--out',str(out)];subprocess.run(cmd,check=True)
 assert all(prep.sha(Path(p))==h for p,h in original_hashes.items()),'Reference campaign mutated'
 assert subprocess.run(cmd,capture_output=True).returncode!=0,'Existing output overwrite allowed'
 yall=out/'Yallfile';subprocess.run([sys.executable,'-m','yall_run.cli','validate',str(yall)],check=True)
 worker=prep.module(out/'boundary_fullchains.py','tested_worker');b=worker.base_module(out)
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
 print('PASS: 233-task DAG; isolated snapshots; original references unchanged; R8 only B2; four-way joins and H deltas verified.')
if __name__=='__main__':main()
