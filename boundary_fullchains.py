#!/usr/bin/env python3
"""Worker for isolated original-vs-valley comparisons, both evaluators."""
import argparse,csv,hashlib,importlib.util,json,math,sys
from pathlib import Path

def stages(code):return ('mip','select')+tuple('refine'+str(n) for n in range(1,9 if code=='b2' else 6))
def base_module(out):
 spec=importlib.util.spec_from_file_location('campaign_base',out/'adaptive_fulltests_base.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
 b.SPECS=b.load(out/'manifest.json')['specs'];return b

def numeric(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None

def common_input(b,out,code):
 """Verify a surviving pre-MIP copy before publishing the DAG's ready marker."""
 incoming=b.load(out/'manifest.json')['inputs'][code]
 if incoming.get('mode')!='transfer':raise ValueError('Boundary comparison requires original pre-MIP transfer input')
 expected=incoming['expected_transfer'];ready=out/'inputs'/code/'ready.json'
 if ready.exists():raise ValueError('Preserving existing verified input: '+str(ready))
 b.check_sources(out,'legacy');b.environment(out,'legacy')
 failures=[];verified=None
 for info in incoming['transfer_candidates']:
  try:
   b.check_info(info)
   print('Checking original pre-MIP SHA-256: '+info['path'],flush=True)
   actual=b.file_info(info['path'],hashed=True)
   b.check_info(info)  # Also reject a file modified during the hash read.
   if actual['size']!=expected['size'] or actual['sha256']!=expected['sha256']:
    raise ValueError('SHA-256 differs from original input')
   verified=actual;break
  except (OSError,ValueError) as e:failures.append(info['path']+': '+str(e))
 if verified is None:raise ValueError('No byte-identical original pre-MIP input for '+code+'; '+ '; '.join(failures))
 trees=b.check_root(Path(verified['path']),events=True)
 if trees!=incoming['expected_trees']:raise ValueError('Original event-tree counts differ: '+code)
 b.check_info(verified)
 ready.parent.mkdir(parents=True,exist_ok=True)
 temporary=ready.with_suffix('.json.tmp')
 b.dump(temporary,dict(transfer=verified,trees=trees,boundary='before initial MIP calibration',mode='transfer',verified_against_original=True,original_ready_sha256=incoming['original_ready_sha256']))
 temporary.replace(ready)
 print('Verified original input for '+code.upper()+': '+verified['path'],flush=True)

def selection_ready(out,model,code):return out/'inputs'/model/code/'ready.json'

def reuse_initial_reports(b,out):
 """Keep original MIP/selection statistics, explicitly marked as reused."""
 for code in b.SPECS:
  for model in b.MODELS:
   for stage in ('mip','select'):
    reference=out/'references'/model/code/stage;p=b.paths(out,model,code,stage)
    p['directory'].mkdir(parents=True,exist_ok=True)
    report=b.load(reference/'stage.json');report['original_execution']=report.pop('execution',{})
    report.update(execution_origin='reused_original',reference=str(reference/'stage.json'))
    if stage=='mip':
     rows=list(csv.DictReader((reference/'cells.csv').open()))
     for r in rows:
      r['carried_forward']=r['fit_saved']!='True' and int(r['bc'])>=2 and numeric(r['scale_h']) is not None
      r.update(range_status='not_refinement',execution_origin='reused_original')
     b.write_csv(p['report'],rows)
     report.update(carried_forward=sum(r['carried_forward'] for r in rows),range_counts={'not_refinement':len(rows)},range_attempts=0)
    b.dump(p['summary'],report)

def snapshot_selection(b,out,model,code):
 """Copy and fingerprint surviving selected events before any new calibration."""
 m=b.load(out/'manifest.json')
 if not m.get('reuse_selection'):raise ValueError('Selection snapshots require --reuse-selection preparation')
 incoming=m['selection_inputs'][code][model];source=incoming['file'];reference=out/incoming['reference']
 if b.digest(reference)!=incoming['reference_sha256']:raise ValueError('Original selection report changed')
 record=b.load(reference)
 if (record.get('model'),record.get('dataset'),record.get('stage'))!=(model,code,'select'):raise ValueError('Original selection identity mismatch')
 b.check_sources(out,model);b.environment(out,model);b.check_info(source)
 target=b.paths(out,model,code,'select')['root'];ready=selection_ready(out,model,code)
 if target.exists() or ready.exists():raise ValueError('Preserving existing selection snapshot: '+str(target))
 target.parent.mkdir(parents=True,exist_ok=True);partial=target.with_suffix('.root.partial')
 if partial.exists():raise ValueError('Preserving incomplete selection snapshot: '+str(partial))
 digest=hashlib.sha256();copied=0
 print(f'Copying {model} {code.upper()} selection ({source["size"]/1e9:.2f} GB): {source["path"]}',flush=True)
 try:
  with Path(source['path']).open('rb') as src,partial.open('xb') as dest:
   while True:
    chunk=src.read(8*1024*1024)
    if not chunk:break
    dest.write(chunk);digest.update(chunk);copied+=len(chunk)
  b.check_info(source)
  if copied!=source['size'] or b.digest(partial)!=digest.hexdigest():raise ValueError('Selection snapshot differs from bytes read from original')
  trees=b.check_root(partial,events=True)
  if trees!=incoming['event_trees'] or trees!=record['event_trees']:raise ValueError('Original selected-event tree counts differ')
  b.check_info(source)
  partial.chmod(0o444);partial.replace(target)
 except BaseException:
  if partial.exists():partial.unlink()
  raise
 ready.parent.mkdir(parents=True,exist_ok=True);temporary=ready.with_suffix('.json.tmp')
 b.dump(temporary,dict(model=model,dataset=code,boundary='after original event selection; before refine1',selected=dict(b.file_info(target),sha256=digest.hexdigest()),original_selected=dict(source,sha256=digest.hexdigest()),event_trees=trees,reference_sha256=incoming['reference_sha256'],fingerprint_scope='SHA-256 established while copying the surviving original selection; original selection report records tree counts, not a historic file hash.'))
 temporary.replace(ready)
 print(f'Verified {model} {code.upper()} selection snapshot: {target}',flush=True)

def check_selection(b,out,model,code):
 ready=b.load(selection_ready(out,model,code));expected=b.paths(out,model,code,'select')['root'].resolve()
 if (ready.get('model'),ready.get('dataset'))!=(model,code) or Path(ready['selected']['path'])!=expected:raise ValueError('Selection snapshot belongs to a different method/dataset')
 b.check_info(ready['selected'])

def audit(b,out,model,code,stage):
 b.audit_stage(out,model,code,stage)
 if stage=='select':return
 p=b.paths(out,model,code,stage);decisions={}
 for line in (p['directory']/'DataPrep.log').read_text(errors='replace').splitlines():
  if not line.startswith('LFHCAL_RANGE_V1 '):continue
  fields=dict(token.split('=',1) for token in line.split()[1:])
  if fields['sample']!='mipTrigg':continue
  cell=int(fields['cell'])
  if cell in decisions:raise ValueError('Duplicate triggered boundary decision for cell '+str(cell))
  decisions[cell]=dict(range_status=fields['status'],range_usable=fields['usable'] in ('1','true'),**{'range_'+k:numeric(fields[k]) for k in ('old','new','peak','valley','fraction')})
 rows=list(csv.DictReader(p['report'].open()))
 if stage.startswith('refine') and not decisions:raise ValueError('No refinement boundary diagnostics; wrong binary or log format')
 counts={}
 for r in rows:
  cell=int(r['cell_id']);r.update(decisions.get(cell,dict(range_status='not_refinement' if stage=='mip' else 'not_attempted')));status=r['range_status'];counts[status]=counts.get(status,0)+1
  if stage.startswith('refine') and r['fit_saved']=='True':
   if cell not in decisions or abs(float(r['fit_xmin'])-decisions[cell]['range_new'])>1e-9:raise ValueError('Saved fit range differs from boundary decision: '+str(cell))
  r['carried_forward']=r['fit_saved']!='True' and int(r['bc'])>=2 and numeric(r['scale_h']) is not None
 b.write_csv(p['report'],rows);report=b.load(p['summary']);report.update(carried_forward=sum(r['carried_forward'] for r in rows),range_counts=counts,range_attempts=len(decisions));b.dump(p['summary'],report)
 b.dump(p['directory']/'range-audit.json',dict(rule='mip_range_v1',counts=counts,cells=decisions))

def build(b,out,model):
 source=b.check_sources(out,model);exe=out/f'test-mip-range-{model}'
 b.run(['c++','-std=c++17','-O2','-I',source/'NewStructure',source/'NewStructure/tests/test_mip_range.cc','-o',exe],source,out/f'range-build-{model}.log',120)
 b.run([exe],source,out/f'range-test-{model}.log',60)
 b.build(out,model)
 version=b.load(out/f'build-{model}.json')['root_version'];expected=b.load(out/'manifest.json')['reference_root_version']
 if version!=expected:raise ValueError(f'Comparison requires original ROOT {expected}; worker has {version}')

def run_stage(b,out,model,code,stage):
 if b.load(out/'manifest.json').get('reuse_selection'):
  if stage in ('mip','select'):raise ValueError('Initial MIP/selection are explicitly reused in this campaign')
  check_selection(b,out,model,code)
 source=b.check_sources(out,model);exe,env=b.environment(out,model);p=b.paths(out,model,code,stage)
 if p['directory'].exists() and any(p['directory'].iterdir()):raise ValueError('Preserving existing stage: '+str(p['directory']))
 p['directory'].mkdir(parents=True,exist_ok=True);(p['directory']/'plots').mkdir(exist_ok=True)
 timing=b.run(b.stage_command(out,model,code,stage,exe),source/'NewStructure',p['directory']/'DataPrep.log',timeout=8*3600,env=env)
 b.run([sys.executable,Path(__file__).resolve(),'audit','--out',out,'--model',model,'--dataset',code,'--stage',stage],source/'NewStructure',p['directory']/'audit.log',1200,env)
 r=b.load(p['summary']);r['execution']=timing;r['execution_origin']='new_run';b.dump(p['summary'],r)

def compare(b,out,code):
 b.STAGES=stages(code);b.compare(out,code);rows=[];stage_rows=[]
 for info in b.load(out/'manifest.json')['reference_files']:
  if Path(info['copy']).parts[2]==code and b.digest(out/info['copy'])!=info['sha256']:raise ValueError('Frozen reference changed: '+info['copy'])
 for stage in stages(code):
  for model in b.MODELS:
   p=b.paths(out,model,code,stage);reference=out/'references'/model/code/stage
   before=b.load(reference/'stage.json');after=b.load(p['summary']);stage_rows.append(dict(stage=stage,model=model,original=before,valley=after))
   if stage=='select':continue
   old={int(r['cell_id']):r for r in csv.DictReader((reference/'cells.csv').open())};new={int(r['cell_id']):r for r in csv.DictReader(p['report'].open())}
   if old.keys()!=new.keys():raise ValueError('Original/new cell IDs differ')
   previous={}
   n=int(stage[6:]) if stage.startswith('refine') else 0
   if n>1:previous={int(r['cell_id']):r for r in csv.DictReader(b.paths(out,model,code,f'refine{n-1}')['report'].open())}
   for cell in sorted(old):
    a,c=old[cell],new[cell];row=dict(dataset=code,stage=stage,model=model,cell_id=cell,execution_origin=after.get('execution_origin','new_run'),original_saved=a['fit_saved'],valley_saved=c['fit_saved'],valley_carried_forward=c['carried_forward'],range_status=c['range_status'],range_usable=c.get('range_usable'),range_old=c.get('range_old'),range_new=c.get('range_new'),same_histogram=a.get('histogram_sha256') not in ('',None,'?') and a.get('histogram_sha256')==c.get('histogram_sha256'))
    for name in ('scale_h','fwhm_h','entries','landau_width','mpv','area','gaussian_sigma','fit_xmin','fit_xmax'):
     x,y=numeric(a.get(name)),numeric(c.get(name));row['original_'+name]=x;row['valley_'+name]=y;row['relative_change_'+name]=(y-x)/x if x not in (None,0) and y is not None else None
    x=numeric(previous.get(cell,{}).get('scale_h'));y=numeric(c['scale_h']);row['previous_refinement_H_change']=(y-x)/x if x not in (None,0) and y is not None else None;rows.append(row)
 b.write_csv(out/'reports'/f'{code}-boundary-comparison.csv',rows);b.dump(out/'reports'/f'{code}-four-way-stages.json',stage_rows)

def summary(b,out):
 cells=[];stages_out=[]
 for code in b.SPECS:
  cells.extend(csv.DictReader((out/'reports'/f'{code}-boundary-comparison.csv').open()))
  for r in b.load(out/'reports'/f'{code}-four-way-stages.json'):
   if r['stage']=='select':continue
   for boundary in ('original','valley'):
    a=r[boundary];saved=a['saved_fits'];available=a['available_calibrations'];stages_out.append(dict(dataset=code,stage=r['stage'],method=r['model'],boundary=boundary,execution_origin='original_reference' if boundary=='original' else a.get('execution_origin','new_run'),saved=saved,available=available,carried_forward=a.get('carried_forward',available-saved),selected_entries=a['total_trigger_entries'],mean_H=a['mean_scale_h'],range_counts=json.dumps(a.get('range_counts',{}),sort_keys=True),wall_s=a.get('execution',{}).get('wall_s')))
 b.write_csv(out/'all-cell-boundary-comparisons.csv',cells);b.write_csv(out/'all-stage-statistics.csv',stages_out)
 resume=b.load(out/'manifest.json').get('reuse_selection',False)
 b.dump(out/'summary.json',dict(scope='14 sets; both evaluators; R5 everywhere and B2 through R8',reuse_selection=resume,initial_stages='Reused original MIP and selection; all refinements rerun.' if resume else 'New full chains from verified original pre-MIP inputs.',stages=stages_out,production_updated=False,scientific_acceptance='Review shifts, convergence, range flags and spectra; optimizer acceptance alone is insufficient.'))

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['build','input','selection','stage','audit','compare','summary']);p.add_argument('--out',required=True,type=Path);p.add_argument('--model',choices=['legacy','adaptive']);p.add_argument('--dataset');p.add_argument('--stage');a=p.parse_args();a.out=a.out.resolve();b=base_module(a.out)
 if a.dataset and a.dataset not in b.SPECS:p.error('Unknown dataset')
 for arg in {'build':['model'],'input':['dataset'],'selection':['model','dataset'],'stage':['model','dataset','stage'],'audit':['model','dataset','stage'],'compare':['dataset'],'summary':[]}[a.action]:
  if getattr(a,arg) is None:p.error('Missing --'+arg)
 if a.stage and a.stage not in stages(a.dataset):p.error('Stage outside this dataset plan')
 if a.action=='build':build(b,a.out,a.model)
 elif a.action=='input':common_input(b,a.out,a.dataset)
 elif a.action=='selection':snapshot_selection(b,a.out,a.model,a.dataset)
 elif a.action=='stage':run_stage(b,a.out,a.model,a.dataset,a.stage)
 elif a.action=='audit':audit(b,a.out,a.model,a.dataset,a.stage)
 elif a.action=='compare':compare(b,a.out,a.dataset)
 else:summary(b,a.out)
if __name__=='__main__':main()
