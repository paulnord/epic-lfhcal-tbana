#!/usr/bin/env python3
"""User-run preservation snapshot. Default inventory only; never submits or deletes.
A verified byte copy is not proof of scientific completeness or restorability.
"""
import argparse, hashlib, json, os, pathlib, re, shutil, stat, subprocess, sys, shlex
from datetime import datetime, timezone
P=pathlib.Path
ROOTS=['/gpfs01/star/scratch/pnord/ari-rebuild-eX4Mld',
 '/gpfs01/star/scratch/pnord/ari-run302-annotations-bdLvhL',
 '/gpfs01/star/scratch/pnord/ari-run302-20261103T003837Z']
PARENT=P('/gpfs01/star/pwg/pnord/eic/2026TBanalysis')
RAW=P('/gpfs01/star/pwg/pnord/eic/2026TBdata/raw')
RUNS={298,300,302,304,306,310,329,333,335,337,339,341,343,345,347,349,351,353,355,357,359,361,363}

def command(args):
 env=os.environ.copy()
 env['GIT_OPTIONAL_LOCKS']='0'
 r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
 return {'command':args,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
def fingerprint(p):
 s=p.lstat(); return [s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''): h.update(block)
 return h.hexdigest()
def within(p,root): return p==root or root in p.parents

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--source',action='append',default=[],help='Additional verified workspace; defaults always included')
 ap.add_argument('--summary',action='store_true',help='Print compact inventory summary instead of full JSON')
 ap.add_argument('--copy',action='store_true',help='Copy only after reviewing inventory, quiescing writers and quota')
 ap.add_argument('--destination',type=P,help='NEW direct child of verified PWG analysis parent')
 ap.add_argument('--sources-quiescent',action='store_true',help='User confirms no jobs/writers modifying these sources')
 ap.add_argument('--quota-reviewed',action='store_true',help='User checked applicable PWG user/group quota, not only df')
 a=ap.parse_args()
 os.umask(0o077)
 if a.copy and (not a.destination or not a.sources_quiescent or not a.quota_reviewed):
  ap.error('--copy requires --destination, --sources-quiescent and --quota-reviewed')
 roots=list(dict.fromkeys(P(x).resolve() for x in ROOTS+a.source))
 files={}; links={}; raw={}; refs={}; issues=[]; manifests=[]; repos={}; seen=set(); directories={}
 def addfile(p):
  p=P(p)
  if p.is_symlink():
   links[str(p)]={'target':os.readlink(p),'resolved':str(p.resolve()),'fingerprint':fingerprint(p)}
   target=p.resolve()
   if not target.exists(): issues.append('Broken symlink: '+str(p))
   elif not any(within(target,r) for r in roots):
    if target.is_file(): addfile(target)
    else: issues.append('External directory symlink needs explicit --source: '+str(p)+' -> '+str(target))
   return
  if not p.is_file(): issues.append('Missing/nonregular dependency: '+str(p)); return
  if p.suffix=='.h2g' or within(p.resolve(),RAW.resolve()):
   raw[str(p)]={'realpath':str(p.resolve()),'fingerprint':fingerprint(p)}
   if not within(p.resolve(),RAW.resolve()): issues.append('Raw source outside persistent PWG; recorded, not copied: '+str(p))
   return
  if not any(within(p.resolve(),r) for r in roots) and '/star/scratch/pnord/' not in str(p.resolve()):
   issues.append('External non-scratch file recorded, not copied; review explicitly: '+str(p)); return
  files[str(p)]={'fingerprint':fingerprint(p)}
 def walk_json(obj,origin):
  if isinstance(obj,dict):
   for k,v in obj.items():
    # Proof/checksum maps encode file paths as keys.
    if str(k).startswith(('/gpfs01/','/gpfs/mnt/gpfs01/','/star/')): refs.setdefault(k,[]).append(origin)
    walk_json(v,origin+'/'+str(k))
  elif isinstance(obj,list):
   for i,v in enumerate(obj):walk_json(v,origin+'/'+str(i))
  elif isinstance(obj,str):
   try: tokens=shlex.split(obj)
   except ValueError: tokens=[obj]
   for token in tokens:
    if token.startswith(('/gpfs01/','/gpfs/mnt/gpfs01/','/star/')) and '\n' not in token:
     refs.setdefault(token,[]).append(origin)
 def scan(root):
  if not root.is_dir(): issues.append('Missing workspace: '+str(root)); return
  for d,dirs,names in os.walk(root,followlinks=False):
   d=P(d); directories[str(d)]=fingerprint(d)
   if '.git' in dirs or '.git' in names: repos[str(d)]={}; dirs[:]=[x for x in dirs if x!='.git']
   for name in dirs[:]:
    if (d/name).is_symlink():addfile(d/name);dirs.remove(name)
   for name in names:
    p=d/name
    if name=='.git':continue # bundle and Git metadata captured separately, not dangling gitdir pointer
    addfile(p)
    if name in ('rf-campaign.txt','other-campaign.txt','campaign-path.txt','campaign.path'):
     try:walk_json(p.read_text(),str(p))
     except Exception as e:issues.append('Unreadable campaign pointer '+str(p)+': '+str(e))
    if name in ('campaign.json','preparation.json','inputs.json'):
     manifests.append(str(p))
     try:
      if p.stat().st_size>16*1024*1024:raise ValueError('Manifest exceeds 16 MiB review limit')
      walk_json(json.loads(p.read_text()),str(p))
     except Exception as e:issues.append('Unreadable manifest '+str(p)+': '+str(e))
 for root in roots:scan(root)
 # Follow exact files and exact campaign metadata trees, never arbitrary home directories.
 while True:
  pending=[v for v in refs if v not in seen]
  if not pending:break
  for value in pending:
   seen.add(value);p=P(value)
   if p.is_file() or p.is_symlink():addfile(p)
   elif not p.exists():issues.append('Missing manifest reference: '+value)
   elif not any(within(p.resolve(),r) for r in roots):
    if (p/'campaign.json').is_file() and '/star/scratch/pnord/' in str(p.resolve()):
     scan(p.resolve())
    else:issues.append('External directory reference needs review/additional --source: '+value)
 for repo in repos:
  for key,args in {'commit':['rev-parse','HEAD'],'status':['status','--porcelain=v1','--untracked-files=all'],
   'diff':['diff','--binary','HEAD'],'staged_diff':['diff','--binary','--cached'],
   'common_dir':['rev-parse','--git-common-dir'],'refs':['show-ref','--head'],'submodules':['submodule','status','--recursive']}.items():
   repos[repo][key]=command(['git','-C',repo]+args)
  metadata=repos[repo]
  metadata['valid_for_bundle']=all(metadata[k]['returncode']==0 for k in ('commit','status','diff','staged_diff','common_dir','refs'))
  if not metadata['valid_for_bundle']:
   issues.append('Git provenance unavailable; preserving existing administrative bytes without claiming valid history: '+repo)
   admin=P(repo)/'.git'
   metadata['administrative_bytes_preserved']=str(admin)
   # Preserve failed parent's admin data, including independently valid modules.
   # Never dereference symlinks here or follow a gitdir pointer automatically.
   entries=[]
   if admin.is_symlink() or admin.is_file():entries=[admin]
   elif admin.is_dir():
    for d,ds,ns in os.walk(admin,followlinks=False):
     directories[d]=fingerprint(P(d))
     for n in ds[:]:
      q=P(d)/n
      if q.is_symlink():entries.append(q);ds.remove(n)
     entries.extend(P(d)/n for n in ns)
   for q in entries:
    if q.is_symlink():
     links[str(q)]={'target':os.readlink(q),'resolved':str(q.resolve()),'fingerprint':fingerprint(q)}
     issues.append('Git admin symlink retained without following target: '+str(q))
    elif q.is_file():files[str(q)]={'fingerprint':fingerprint(q)}
    else:issues.append('Nonregular Git administrative entry: '+str(q))
  # Initialized submodule worktrees are independently discovered and bundled.
  if metadata['submodules']['returncode']:
   issues.append('Submodule inventory unavailable; review discovered checkout list: '+repo)
  elif metadata['submodules']['stdout'].strip():
   for line in metadata['submodules']['stdout'].splitlines():
    fields=line.split()
    if len(fields)>1 and str((P(repo)/fields[1]).resolve()) not in repos:
     issues.append('Submodule not independently discovered; review history: '+line)
 # Canonicalize aliases to prevent duplicate GPFS mount spellings.
 canonical={}
 for name,item in files.items():
  real=str(P(name).resolve());canonical.setdefault(real,{'fingerprint':fingerprint(P(real)),'aliases':[]})['aliases'].append(name)
 files=canonical
 readable_nonempty={name for name,x in files.items() if x['fingerprint'][3]>0 and os.access(name,os.R_OK)}
 present={int(m.group(1)) for name in readable_nonempty for m in [re.search(r'calibratedHGCROC_Run_(\d+)\.root$',name)] if m}
 hists={int(m.group(1)) for name in readable_nonempty for m in [re.search(r'calibratedHGCROC_wave_Run_(\d+)_Hists\.root$',name)] if m}
 csvs={int(m.group(1)) for name in readable_nonempty for m in [re.search(r'WaveformGrid_Run(\d+)_Measurements\.csv$',name)] if m}
 missing=sorted(RUNS-present)
 if RUNS-hists:issues.append('Missing waveform histogram outputs: '+','.join(map(str,sorted(RUNS-hists))))
 if RUNS-csvs:issues.append('Missing waveform measurement CSVs: '+','.join(map(str,sorted(RUNS-csvs))))
 if missing:issues.append('Missing calibrated event inputs for runs: '+','.join(map(str,missing)))
 report={'utc':datetime.now(timezone.utc).isoformat(),'roots':list(map(str,roots)),
  'files':files,'symlinks':links,'raw_references_not_copied':raw,'manifest_references':refs,
  'manifests':manifests,'git':repos,'issues':sorted(set(issues)),
  'coverage':{'meaning':'Nonempty readable file presence only; not scientific validation','expected_runs':sorted(RUNS),'calibrated_runs_present':sorted(present),'calibrated_runs_missing':missing,'waveform_histogram_runs_present':sorted(hists),'waveform_histogram_runs_missing':sorted(RUNS-hists),'measurement_csv_runs_present':sorted(csvs),'measurement_csv_runs_missing':sorted(RUNS-csvs)},
  'copy_bytes':sum(x['fingerprint'][3] for x in files.values()),
  'restorability':'NOT_CERTIFIED: review references, symlink relocation, campaign completion and scientific run coverage'}
 if not a.copy:
  if a.summary:
   summary={k:report[k] for k in ('roots','coverage','copy_bytes','issues','restorability')}
   summary['issue_count']=len(report['issues'])
   summary['issues']=report['issues'][:20]
   summary['issues_truncated']=len(report['issues'])>20
   summary['git_checkouts']={r:{'valid_for_bundle':d['valid_for_bundle'],'commit':d['commit']['stdout'].strip(),'commit_error':d['commit']['stderr'].strip()} for r,d in repos.items()}
   print(json.dumps(summary,indent=2))
  else:print(json.dumps(report,indent=2))
  return
 dest=a.destination.absolute()
 if dest.parent.resolve()!=PARENT.resolve() or not PARENT.is_dir():raise RuntimeError('Destination must be a new direct child of existing PWG analysis parent')
 if dest.exists() or dest.is_symlink():raise RuntimeError('Destination already exists; never overwrite or resume')
 if any(within(dest.resolve(),r) or within(r,dest.resolve()) for r in roots):raise RuntimeError('Overlapping source/destination')
 if shutil.disk_usage(PARENT).free < report['copy_bytes']:raise RuntimeError('Insufficient filesystem space (quota still separately required)')
 dest.mkdir(mode=0o700) # exclusive; a failed snapshot is left in place for inspection
 (dest/'SNAPSHOT_STARTED').write_text('Snapshot started. Only COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED indicates byte verification finished. No completeness claim.\n')
 meta=dest/'metadata';meta.mkdir()
 (meta/'inventory-before.json').write_text(json.dumps(report,indent=2))
 # Preflight EVERY valid Git bundle before creating/copying any payload.
 for i,(repo,metadata) in enumerate(repos.items()):
  if not metadata['valid_for_bundle']:continue
  bundle=meta/('source-%03d.bundle'%i)
  r=command(['git','-C',repo,'bundle','create',str(bundle),'--all','HEAD'])
  if r['returncode']:raise RuntimeError('Git bundle failed: '+r['stderr'])
  r=command(['git','-C',repo,'bundle','verify',str(bundle)])
  if r['returncode']:raise RuntimeError('Git bundle verification failed: '+r['stderr'])
  metadata['bundle']={'path':str(bundle.relative_to(dest)),'sha256':sha(bundle)}
  for key,args in [('commit',['rev-parse','HEAD']),('status',['status','--porcelain=v1','--untracked-files=all']),('diff',['diff','--binary','HEAD']),('staged_diff',['diff','--binary','--cached']),('refs',['show-ref','--head'])]:
   if command(['git','-C',repo]+args)!=metadata[key]:raise RuntimeError('Git source changed during preflight: '+repo)
 payload=dest/'payload';payload.mkdir()
 # Original absolute paths represented beneath payload/. Symlinks retained and reported;
 # external file targets are copied separately, never silently dereferenced or overwritten.
 for name,item in files.items():
  src=P(name);out=payload/name.lstrip('/');out.parent.mkdir(parents=True,exist_ok=True)
  if fingerprint(src)!=item['fingerprint']:raise RuntimeError('Source changed before copy: '+name)
  digest=sha(src)
  with src.open('rb') as fi,out.open('xb') as fo:shutil.copyfileobj(fi,fo,8*1024*1024)
  shutil.copystat(src,out)
  if sha(out)!=digest or fingerprint(src)!=item['fingerprint'] or sha(src)!=digest:raise RuntimeError('Copy mismatch or source changed: '+name)
  item['sha256']=digest;item['archive_relative']=str(out.relative_to(dest))
 for name,item in links.items():
  src=P(name)
  if fingerprint(src)!=item['fingerprint'] or os.readlink(src)!=item['target']:raise RuntimeError('Symlink changed: '+name)
  out=payload/name.lstrip('/');out.parent.mkdir(parents=True,exist_ok=True)
  target=payload/item['resolved'].lstrip('/')
  if item['resolved'] in files or target.is_dir():
   relative=os.path.relpath(str(target),str(out.parent));out.symlink_to(relative);item['archived_target']=relative
  else:
   out.symlink_to(item['target']);item['archived_target']=item['target']
   issues.append('Unrelocated symlink: '+name)
 for name,item in raw.items():
  p=P(name);item['integrity']='Path and stat recorded only; use existing raw archive checksum records if available'
  if fingerprint(p)!=item['fingerprint']:raise RuntimeError('Raw reference changed: '+name)
 for repo,metadata in repos.items():
  if not metadata['valid_for_bundle']:continue
  for key,args in [('commit',['rev-parse','HEAD']),('status',['status','--porcelain=v1','--untracked-files=all']),('diff',['diff','--binary','HEAD']),('staged_diff',['diff','--binary','--cached']),('refs',['show-ref','--head'])]:
   if command(['git','-C',repo]+args)!=metadata[key]:raise RuntimeError('Git source changed: '+repo)
 for name,item in files.items():
  if fingerprint(P(name))!=item['fingerprint']:raise RuntimeError('Source changed during snapshot: '+name)
 for name,item in links.items():
  if fingerprint(P(name))!=item['fingerprint'] or os.readlink(name)!=item['target']:raise RuntimeError('Symlink changed during snapshot: '+name)
 for name,item in raw.items():
  if fingerprint(P(name))!=item['fingerprint']:raise RuntimeError('Raw reference changed during snapshot: '+name)
 for name,fp in directories.items():
  if fingerprint(P(name))!=fp:raise RuntimeError('Directory changed during snapshot: '+name)
 report['issues']=sorted(set(issues))
 (meta/'verified-inventory.json').write_text(json.dumps(report,indent=2))
 (meta/'SHA256SUMS').write_text(''.join(x['sha256']+'  '+x['archive_relative']+'\n' for x in files.values())+''.join(r['bundle']['sha256']+'  '+r['bundle']['path']+'\n' for r in repos.values() if 'bundle' in r))
 # Keep startup marker; final marker distinguishes byte verification.
 (dest/'COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED').write_text('Payload files checksum verified. Original sources unchanged by recorded fingerprints. Review metadata issues; absolute symlinks and original manifest paths need relocation. This does NOT certify all analysis is complete.\n')
 print('Byte copy verified:',dest)
 print('Restorability NOT certified. Review metadata/verified-inventory.json. Issue count:',len(report['issues']))
if __name__=='__main__':
 try:main()
 except Exception as e:print('STOP:',e,file=sys.stderr);sys.exit(1)
