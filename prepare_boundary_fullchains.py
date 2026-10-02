#!/usr/bin/env python3
"""Prepare an isolated 233-task Legacy/Adaptive valley-boundary campaign.
Reads original campaign snapshots and references; never submits jobs.
"""
import argparse,csv,hashlib,importlib.util,json,os,shutil,subprocess,sys,time
from pathlib import Path
EARLY='adaptive-fullchains-20260928T223211Z'
REMAINING='adaptive-fullchains-remaining-20260929T014858Z'
RECOVERY='adaptive-d1-recovery-20260929T164711Z'
EXTENSION='b2-r6-r8-20261001'
BASE_RUNNER_SHA='32854a25b3d9fc4873d26d2a4e706d64a7b8319dfa55dd92dd98b1f8858f6054'
CODES=('b1','b2','c1','c2','c3','d1','d2','e1','e2','e3','f1','f2','g1','g2')
DEFAULT_ARCHIVE=Path('/gpfs01/star/pwg/pnord/eic/2026TBanalysis')
PAYLOADS={'boundary_fullchains.py':'boundary_fullchains.py','apply_mip_range.py':'apply_mip_range.py','MipRangeFinder.h':'NewStructure/MipRangeFinder.h','test_mip_range.cc':'NewStructure/tests/test_mip_range.cc'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def dump(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def git(repo,*args):return subprocess.check_output(['git','-C',str(repo),*args])
def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def input_index(roots, names):
 """Find exact pre-MIP basenames, without opening large ROOT files on login nodes."""
 found={name:[] for name in names};warnings=[]
 for root in dict.fromkeys(Path(p).resolve() for p in roots):
  if not root.is_dir():continue
  for directory,dirs,files in os.walk(root,onerror=lambda e:warnings.append(str(e))):
   here=Path(directory);depth=len(here.relative_to(root).parts)
   dirs[:]=sorted(d for d in dirs if depth<4 and not d.startswith('.') and d not in ('sources','build','plots','campaigns','reports'))
   for name in sorted(names.intersection(files)):found[name].append(here/name)
 return found,warnings

def resolve_input(b, code, original, ready_path, indexed, roots):
 """Bind candidates to the original worker's hash, never to a filename alone."""
 if original.get('mode')!='transfer':raise ValueError('Expected original pre-MIP transfer input')
 ready=load(ready_path);expected=ready['transfer'];digest=expected.get('sha256','')
 if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Missing valid original transfer SHA-256 in '+str(ready_path))
 if ready.get('boundary')!='before initial MIP calibration':raise ValueError('Original input record is not pre-MIP: '+str(ready_path))
 recorded=original['files']['transfer']
 # Same original path/size; mtime may legitimately change when an identical file is copied.
 if Path(expected['path'])!=Path(recorded['path']) or expected['size']!=recorded['size']:raise ValueError('Original manifest/input record disagree: '+str(ready_path))
 name=Path(expected['path']).name
 candidates=[Path(expected['path'])]
 for root in roots:
  candidates.extend([root/name,root/'transfer'/name,root/f'fullset-{code}-repro'/'transfer'/name,root/f'adaptive-fullset-{code}-repro'/'transfer'/name])
 candidates.extend(indexed.get(name,[]));infos=[];seen=set();rejected=[]
 for candidate in candidates:
  if not candidate.is_file():continue
  try:
   info=b.file_info(candidate)
   if info['path'] in seen:continue
   seen.add(info['path'])
   if info['size']!=expected['size']:
    rejected.append(f"{info['path']} ({info['size']} bytes)");continue
   infos.append(info)
  except (OSError,ValueError) as e:rejected.append(str(e))
 if not infos:
  raise ValueError(f"No candidate for {name}; expected {expected['size']} bytes. Original: {expected['path']}"+('; rejected: '+'; '.join(rejected) if rejected else ''))
 return dict(mode='transfer',files={'transfer':infos[0]},transfer_candidates=infos,expected_transfer=expected,expected_trees=ready['trees'],original_ready_path=str(ready_path),original_ready_sha256=sha(ready_path))

def make_yall(out,worker,b):
 m=load(out/'manifest.json');lines=['campaign lfhcal-valley-boundary-fullchains','backend condor','','%cpus 1','%memory 8GB','%disk 16GB','%time 10h','%getenv true',f'%wrapper {out}/run-in-eic-shell.sh {m["eic_shell"]} /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1',''];count=0
 def task(name,deps,cmd,outputs,inputs=(),settings=()):
  nonlocal count
  count+=1;lines.append(name+':'+(' '+' '.join(deps) if deps else ''));lines.extend('    '+s for s in settings)
  for label,path in [('runner',out/'boundary_fullchains.py'),('base',out/'adaptive_fulltests_base.py'),('manifest',out/'manifest.json'),('sources',out/'source-hashes.json')]+list(inputs):lines.append(f'    @input {label} {path}')
  for i,path in enumerate(outputs):lines.append(f'    @output out{i} {path}')
  lines.extend([f'    python3 @input.runner {cmd} --out {out}',''])
 for model in b.MODELS:task('build-'+model,[],f'build --model {model}',[out/f'build-{model}.json'],settings=['%cpus 4','%time 2h'])
 for code in CODES:
  task('input-'+code,['build-legacy','build-adaptive'],f'input --dataset {code}',[out/'inputs'/code/'ready.json'],settings=['%time 24h'])
  for model in b.MODELS:
   previous='input-'+code
   for stage in worker.stages(code):
    p=b.paths(out,model,code,stage);products=[p['root'],p['summary']];inputs=[('build_record',out/f'build-{model}.json')]
    if stage!='select':products.extend([p['calib'],p['hists'],p['report'],p['directory']/'range-audit.json'])
    if stage=='mip':inputs.append(('ready',out/'inputs'/code/'ready.json'))
    elif stage=='select':inputs.append(('initial_events',b.paths(out,model,code,'mip')['root']))
    else:
     inputs.append(('selected_events',b.paths(out,model,code,'select')['root']));n=int(stage[6:])
     if n>1:inputs.append(('previous_calibration',b.paths(out,model,code,f'refine{n-1}')['calib']))
    name=f'{stage}-{model}-{code}';task(name,[previous],f'stage --model {model} --dataset {code} --stage {stage}',products,inputs);previous=name
  final=worker.stages(code)[-1]
  task('compare-'+code,[f'{final}-{model}-{code}' for model in b.MODELS],f'compare --dataset {code}',[out/'reports'/f'{code}-boundary-comparison.csv',out/'reports'/f'{code}-four-way-stages.json',out/'reports'/f'{code}-comparison.csv',out/'reports'/f'{code}-stages.json'])
 task('summary',['compare-'+c for c in CODES],'summary',[out/'summary.json',out/'all-stage-statistics.csv',out/'all-cell-boundary-comparisons.csv'])
 assert count==233;return '\n'.join(lines)+'\n',count

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--ref',default='FETCH_HEAD');ap.add_argument('--work',type=Path,default=Path('/gpfs01/star/scratch/pnord/lfhcal'));ap.add_argument('--archive',type=Path,default=DEFAULT_ARCHIVE);ap.add_argument('--input-root',type=Path,action='append',default=[],help='Additional directory to search for exact original pre-MIP files (repeatable; depth <=4)');ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.work=a.work.resolve();a.out=a.out.resolve();a.repo=a.repo.resolve()
 for path in (a.work,a.out,a.repo):
  if any(ch.isspace() or ch in '{}\"\'' for ch in str(path)):raise ValueError('Use paths without whitespace, braces or quotes')
 if a.out.exists():raise ValueError('Use a new output directory; refusing '+str(a.out))
 for name in (EARLY,REMAINING,RECOVERY,EXTENSION):
  parent=a.work/name
  if a.out==parent or parent in a.out.parents:raise ValueError('Output must be separate from reference campaigns')
 ref=git(a.repo,'rev-parse',a.ref+'^{commit}').decode().strip();payload={name:git(a.repo,'show',ref+':'+path) for name,path in PAYLOADS.items()}
 parents={name:load(a.work/name/'manifest.json') for name in (EARLY,REMAINING)}
 specs={**parents[EARLY]['specs'],**parents[REMAINING]['specs']};assert set(specs)==set(CODES)
 originals={c:(EARLY if c in ('b2','e1','e3') else RECOVERY if c=='d1' else REMAINING) for c in CODES}
 source_parent=a.work/EARLY;source_hashes=load(source_parent/'source-hashes.json');base_path=source_parent/'adaptive_fulltests.py'
 if sha(base_path)!=BASE_RUNNER_SHA:raise ValueError('Original runner is not the reviewed version')
 b=module(base_path,'preparation_base');b.SPECS=specs
 if b.STAGES!=('mip','select','refine1','refine2','refine3','refine4','refine5'):raise ValueError('Unexpected original runner')
 # Require reviewed C++ sources across all original campaigns, not only the copy.
 for name in (EARLY,REMAINING,RECOVERY):
  h=load(a.work/name/'source-hashes.json')
  for model in b.MODELS:
   if h[model]!=source_hashes[model]:raise ValueError('Reference source snapshots differ: '+name+' '+model)
 for model,files in source_hashes.items():
  for rel,expected in files.items():
   p=Path(rel)
   if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe source path')
   if sha(source_parent/'sources'/model/p)!=expected:raise ValueError('Changed original source: '+rel)
 versions={load(a.work/name/f'build-{model}.json')['root_version'] for name in (EARLY,REMAINING,RECOVERY) for model in b.MODELS}
 if len(versions)!=1:raise ValueError('Reference ROOT versions differ')
 shell=Path(parents[EARLY]['eic_shell'])
 if sha(shell)!=parents[EARLY]['eic_shell_sha256']:raise ValueError('EIC shell changed since original run')
 for name,m in parents.items():
  if m['eic_shell_sha256']!=sha(shell):raise ValueError('Original EIC shells differ')
 if sha(source_parent/'run-in-eic-shell.sh')!=sha(a.work/REMAINING/'run-in-eic-shell.sh'):raise ValueError('Original wrappers differ')
 search_roots=list(dict.fromkeys(p.resolve() for p in [a.work,a.archive]+a.input_root))
 names={Path(load(a.work/originals[c]/'manifest.json')['inputs'][c]['files']['transfer']['path']).name for c in CODES}
 indexed,search_warnings=input_index(search_roots,names)
 incoming={};reference_files=[];reference_provenance=[];input_errors=[]
 for c in CODES:
  parent=a.work/originals[c];manifest=load(parent/'manifest.json')
  if manifest.get('specs',{}).get(c)!=specs[c]:raise ValueError('Reference recipe mismatch: '+c)
  # This comparison deliberately reuses the same unselected pre-MIP input.
  ready_path=parent/'inputs'/c/'ready.json'
  try:
   incoming[c]=resolve_input(b,c,manifest['inputs'][c],ready_path,indexed,search_roots)
   reference_files.append((ready_path,Path('references')/'inputs'/c/'ready.json',incoming[c]['original_ready_sha256']))
   first=incoming[c]['files']['transfer']['path'];count=len(incoming[c]['transfer_candidates'])
   print(f'{c.upper()}: {count} pre-MIP candidate(s); first {first}; original SHA-256 will be checked on worker.',flush=True)
  except (OSError,ValueError,KeyError) as e:input_errors.append(f'{c.upper()}: {e}')
  reference_provenance.append(dict(dataset=c,campaign=str(parent),manifest_sha256=sha(parent/'manifest.json')))
  for model in b.MODELS:
   for stage in ('mip','select')+tuple('refine'+str(n) for n in range(1,9 if c=='b2' else 6)):
    root=a.work/EXTENSION if c=='b2' and stage in ('refine6','refine7','refine8') else parent
    folder=root/model/c/stage;record=load(folder/'stage.json')
    if record.get('execution',{}).get('returncode')!=0:raise ValueError('Reference stage not successful: '+str(folder))
    for name in (['stage.json'] if stage=='select' else ['stage.json','cells.csv']):
     src=folder/name;reference_files.append((src,Path('references')/model/c/stage/name,sha(src)))
 if input_errors:
  raise SystemExit('Input preflight failed; no output created or jobs submitted.\n'+'\n'.join(input_errors)+'\nSearched (depth <=4): '+', '.join(map(str,search_roots))+'\nUse --input-root DIR for another archive directory. Only byte-identical pre-MIP inputs are accepted.'+('\nSearch warnings: '+'; '.join(search_warnings) if search_warnings else ''))
 for warning in search_warnings:print('Search warning: '+warning,file=sys.stderr)
 a.out.mkdir(parents=True)
 for name,data in payload.items():(a.out/name).write_bytes(data)
 shutil.copy2(base_path,a.out/'adaptive_fulltests_base.py');shutil.copy2(source_parent/'run-in-eic-shell.sh',a.out/'run-in-eic-shell.sh')
 patcher=module(a.out/'apply_mip_range.py','range_patcher')
 for model,files in source_hashes.items():
  dest=a.out/'sources'/model
  for rel in files:
   p=dest/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_parent/'sources'/model/rel,p)
  patcher.apply(dest,a.out/'MipRangeFinder.h');test=dest/'NewStructure/tests/test_mip_range.cc';test.parent.mkdir(exist_ok=True);shutil.copy2(a.out/'test_mip_range.cc',test)
 copied=[]
 for src,rel,expected in reference_files:
  p=a.out/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,p)
  if sha(p)!=expected:raise ValueError('Reference changed during copy')
  p.chmod(0o444)
  copied.append(dict(original=str(src),copy=str(rel),sha256=expected))
 hashes={model:b.tree_hashes(a.out/'sources'/model) for model in b.MODELS};dump(a.out/'source-hashes.json',hashes)
 for model in b.MODELS:
  changed={p for p,h in hashes[model].items() if source_hashes[model].get(p)!=h}
  if changed!={'NewStructure/TileSpectra.cc','NewStructure/MipRangeFinder.h','NewStructure/tests/test_mip_range.cc'}:raise ValueError('Unexpected source changes: '+repr(changed))
 dump(a.out/'manifest.json',dict(rule='mip_range_v1',test_code_commit=ref,reference_root_version=next(iter(versions)),eic_shell=str(shell),eic_shell_sha256=sha(shell),wrapper_sha256=sha(a.out/'run-in-eic-shell.sh'),inputs=incoming,specs={c:specs[c] for c in CODES},reference_campaigns=reference_provenance,reference_files=copied,source_parent=str(source_parent),original_source_hashes=source_hashes,base_runner_sha256=sha(base_path),payload_hashes={name:sha(a.out/name) for name in payload},created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),scope='Both evaluators; boundary changes only HG HGCROC refinement windows. Initial MIP pass remains original. No fit option, MPV bound, error model or acceptance changes.'))
 worker=module(a.out/'boundary_fullchains.py','range_worker');text,count=make_yall(a.out,worker,b);(a.out/'Yallfile').write_text(text)
 print('Prepared:',a.out);print(f'{count} tasks: 2 builds, 14 shared inputs, 28 full chains, 14 comparisons, summary.');print('R5 for all sets; B2 continues through R8. Both Legacy and Adaptive use the new boundary.');print('Original results copied as read-only references. No jobs submitted.');print('Run yall-run validate and yall-run plan here.')
if __name__=='__main__':main()
