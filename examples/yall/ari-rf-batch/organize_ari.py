#!/usr/bin/env python3
"""Organize the verified Ari archive into a NEW working analyzed directory.
Default is read-only planning. Copies only enumerated successful product trees,
never follows scratch links, never deletes/overwrites, and never submits jobs.
Checksum verification is not scientific/ROOT-structure validation.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys

EXPECTED = {298,300,302,304,306,310,329,333,335,337,339,341,343,345,347,349,351,353,355,357,359,361,363}
STAGES = {'converted','pedestal','transfer','mip','selected','refine1','refine2','refine3','calibrated','waveform','plots'}
PREFIX = '/gpfs01/star/scratch/pnord/'
ROOTS = {
 'rf': PREFIX+'ari-rebuild-eX4Mld/rf/products/',
 'other': PREFIX+'ari-rebuild-eX4Mld/other/products/',
 'run302': PREFIX+'ari-run302-20261103T003837Z/work/products/',
 'run302_annotations': PREFIX+'ari-run302-annotations-bdLvhL/work/products/',
}

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()

def canonical(s):
    return s.replace('/gpfs/mnt/gpfs01/', '/gpfs01/', 1) if s.startswith('/gpfs/mnt/gpfs01/') else s

def safe_relative(s):
    p=PurePosixPath(s)
    if p.is_absolute() or not p.parts or any(x in ('..','.') for x in p.parts):
        raise ValueError('Unsafe relative path: '+s)
    return p

def checked_file(archive, relative):
    p=safe_relative(relative)
    cur=archive
    for part in p.parts:
        cur=cur/part
        if cur.is_symlink(): raise ValueError('Refusing archived symlink: '+str(cur))
    st=cur.stat()
    if not stat.S_ISREG(st.st_mode): raise ValueError('Not a regular archived file: '+str(cur))
    return cur

def target_for(original):
    original=canonical(original)
    for tag,root in ROOTS.items():
        if not original.startswith(root): continue
        rel=original[len(root):]
        p=safe_relative(rel)
        if p.parts[0] not in STAGES: return None
        # New run302 annotation output supersedes the older waveform-only products.
        waveform = p.parts[0]=='waveform' or p.parts[:2]==('plots','waveform')
        if tag=='run302' and waveform: return None
        if tag=='run302_annotations' and not waveform: return None
        if p.suffix.lower() not in {'.root','.txt','.csv','.pdf','.png'}: return None
        return tag,str(p)
    return None

def make_plan(archive, expected=EXPECTED):
    archive=archive.resolve(strict=True)
    marker=archive/'COPY_VERIFIED_RESTORABILITY_REVIEW_REQUIRED'
    if not marker.is_file() or marker.is_symlink(): raise ValueError('Missing byte-verification marker')
    inv=checked_file(archive,'metadata/verified-inventory.json')
    doc=json.loads(inv.read_text())
    selected={}; ignored=0; duplicates=0
    for original,item in doc['files'].items():
        target=target_for(original)
        if target is None: ignored+=1; continue
        tag,relative=target
        checksum=item.get('sha256','')
        if not re.fullmatch('[0-9a-f]{64}',checksum): raise ValueError('Missing archive checksum: '+original)
        src=checked_file(archive,item['archive_relative'])
        size=src.stat().st_size
        if size!=item['fingerprint'][3] or size==0: raise ValueError('Empty/size-changed archived product: '+str(src))
        row={'destination':relative,'archive_relative':item['archive_relative'],'original':original,'source_group':tag,'bytes':size,'sha256':checksum}
        if relative in selected:
            old=selected[relative]
            if old['sha256']!=checksum or old['bytes']!=size: raise ValueError('Conflicting destination: '+relative)
            duplicates+=1; continue
        selected[relative]=row
    files=sorted(selected.values(),key=lambda x:x['destination'])
    coverage={}
    pats={
      'calibrated':r'^calibrated/calibratedHGCROC_Run_(\d+)\.root$',
      'waveform':r'^waveform/calibratedHGCROC_wave_Run_(\d+)_Hists\.root$',
      'measurements':r'^plots/waveform/Run(\d+)/WaveformGrid_Run\1_Measurements\.csv$'}
    for kind,pat in pats.items():
        present={int(m.group(1)) for row in files for m in [re.match(pat,row['destination'])] if m}
        coverage[kind]={'present':sorted(present),'missing':sorted(expected-present)}
        if expected-present: raise ValueError('Missing '+kind+' for runs '+str(sorted(expected-present)))
    if not files: raise ValueError('No products selected')
    plan={'schema':1,'archive':str(archive),'inventory_sha256':digest(inv),'files':files,
          'coverage':coverage,'missing_RF7_run':331,'bytes':sum(x['bytes'] for x in files),
          'counts_by_stage':dict(sorted(Counter(x['destination'].split('/')[0] for x in files).items())),
          'ignored_inventory_entries':ignored,'identical_duplicates':duplicates,
          'validation':'Archive checksum provenance and present file sizes only at planning; ROOT structure and physics not validated.',
          'exclusions':'Interrupted attempts, source/build/campaign trees, old run302 waveform products, and books produced after this archive are not imported.'}
    plan['plan_sha256']=hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return plan,doc

def copy_plan(plan,doc,destination,approved_plan,quota_ok):
    if plan['plan_sha256']!=approved_plan: raise ValueError('Plan hash mismatch: rerun dry run and review')
    if not quota_ok: raise ValueError('Copy requires reviewed quota or explicit acceptance of unknown quota')
    destination=destination.absolute()
    if destination.exists() or destination.is_symlink(): raise ValueError('Destination already exists; never overwrite/resume')
    if not destination.parent.is_dir(): raise ValueError('Destination parent must already exist')
    archive=Path(plan['archive'])
    resolved=destination.parent.resolve()/destination.name
    if resolved==archive or archive in resolved.parents or resolved in archive.parents: raise ValueError('Destination overlaps archive')
    if shutil.disk_usage(destination.parent).free<plan['bytes']+16*1024*1024: raise ValueError('Insufficient filesystem free space (quota is separate)')
    # Exclusive directory: partial failure remains unmistakable and is never resumed blindly.
    destination.mkdir(mode=0o700)
    (destination/'INCOMPLETE').write_text('Import in progress or failed. Do not use until IMPORT_BYTE_VERIFIED exists.\n')
    metadata=destination/'metadata';metadata.mkdir()
    (metadata/'migration-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    (metadata/'source-archive-inventory.json').write_text(json.dumps(doc,indent=2)+'\n')
    for stage in sorted(STAGES|{'comparisons'}): (destination/stage).mkdir(exist_ok=True)
    for index,row in enumerate(plan['files'],1):
        src=checked_file(archive,row['archive_relative'])
        out=destination/row['destination'];out.parent.mkdir(parents=True,exist_ok=True)
        before=src.stat()
        if before.st_size!=row['bytes']: raise ValueError('Source size changed: '+str(src))
        h=hashlib.sha256()
        with src.open('rb') as fi,out.open('xb') as fo:
            for block in iter(lambda:fi.read(8*1024*1024),b''):
                h.update(block);fo.write(block)
        after=src.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino): raise ValueError('Source changed while copying: '+str(src))
        if h.hexdigest()!=row['sha256'] or digest(out)!=row['sha256']: raise ValueError('Checksum mismatch: '+str(src))
        shutil.copystat(src,out)
        if index%100==0: print('Verified %d/%d files'%(index,len(plan['files'])),flush=True)
    (metadata/'SHA256SUMS').write_text(''.join(x['sha256']+'  '+x['destination']+'\n' for x in plan['files']))
    (destination/'README.txt').write_text('Working Ari analysis products imported from a byte-verified archive.\nOriginal archive: '+str(archive)+'\nNo link to scratch is needed to read these data files. Source/config history remains in the original archive and copied metadata.\n23 existing runs imported; RF7/run331 remains to be processed and added.\nROOT structure and scientific validity have NOT been certified by this copy.\nDo not overwrite completed files when reprocessing; retain a separate revision.\n')
    (destination/'IMPORT_BYTE_VERIFIED').write_text(datetime.now(timezone.utc).isoformat()+'\nEvery copied product checked against archive SHA256 and read back. No ROOT or scientific validation claim.\n')
    (destination/'INCOMPLETE').unlink() # only the marker this invocation created
    print('Import byte verified:',destination,flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',required=True,type=Path)
    p.add_argument('--destination',required=True,type=Path)
    p.add_argument('--copy',action='store_true')
    p.add_argument('--plan-sha256')
    q=p.add_mutually_exclusive_group();q.add_argument('--quota-reviewed',action='store_true');q.add_argument('--accept-unknown-quota',action='store_true')
    a=p.parse_args()
    plan,doc=make_plan(a.archive)
    if not a.copy:
        summary={k:v for k,v in plan.items() if k!='files'}
        summary.update(destination=str(a.destination.absolute()),file_count=len(plan['files']),GiB=round(plan['bytes']/2**30,3),mode='READ_ONLY_PLAN')
        print(json.dumps(summary,indent=2));return
    copy_plan(plan,doc,a.destination,a.plan_sha256,a.quota_reviewed or a.accept_unknown_quota)
if __name__=='__main__':
    try: main()
    except Exception as e: print('STOP:',e,file=sys.stderr);sys.exit(1)
