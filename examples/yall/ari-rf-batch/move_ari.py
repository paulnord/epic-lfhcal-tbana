#!/usr/bin/env python3
"""Move indexed Ari products out of the archive. RAW DATA NEVER SELECTED.
Archive becomes incomplete. Same-filesystem, no-overwrite, resumable transfer.
A no-clobber hard link followed by source unlink avoids rename overwrite races.
"""
import argparse,fcntl,json,os,sys
from pathlib import Path
from organize_ari import make_plan,checked_file,digest,safe_relative,STAGES

def valid(p,row):
    if p.is_symlink() or not p.is_file() or p.stat().st_size!=row['bytes'] or digest(p)!=row['sha256']:
        raise ValueError('Invalid file: '+str(p))
def paths(a,d,row):
    src=a/safe_relative(row['archive_relative']);out=d/safe_relative(row['destination'])
    for p,root in ((src,a),(out,d)):
        if any(q.is_symlink() for q in (p,*list(p.parents)[:len(p.relative_to(root).parts)-1])):raise ValueError('Symlink rejected: '+str(p))
    return src,out

def execute(a,d,approved,resume=False,expected=None):
    a=a.resolve();d=d.absolute();r=d.parent.resolve()/d.name
    if r==a or a in r.parents or r in a.parents:raise ValueError('Destination overlaps archive')
    if not d.parent.is_dir() or d.is_symlink():raise ValueError('Invalid destination parent/path')
    if resume:
        if not (d/'INCOMPLETE').is_file():raise ValueError('Resume requires INCOMPLETE marker')
        plan=json.loads((d/'metadata/move-plan.json').read_text())
        if plan['archive']!=str(a) or plan['destination']!=str(d):raise ValueError('Resume paths differ')
    else:
        if d.exists():raise ValueError('Destination exists; use --resume only for this migration')
        plan,doc=make_plan(a) if expected is None else make_plan(a,expected)
        plan['destination']=str(d)
    if plan['plan_sha256']!=approved:raise ValueError('Plan hash mismatch')
    # Full preflight before any new source removals; resume accepts only proven states.
    for row in plan['files']:
        src,out=paths(a,d,row)
        if src.exists():
            checked_file(a,row['archive_relative']);valid(src,row)
            if src.stat().st_dev!=d.parent.stat().st_dev:raise ValueError('Cross-filesystem move refused')
            if out.exists():
                if not resume or not os.path.samefile(src,out):raise ValueError('Destination collision: '+str(out))
                valid(out,row)
        elif resume:valid(out,row)
        else:raise ValueError('Missing source: '+str(src))
    if not resume:
        d.mkdir(mode=0o700);(d/'metadata').mkdir()
        (d/'INCOMPLETE').write_text('Move in progress; resume with same command plus --resume.\n')
        with (d/'metadata/move-plan.json').open('x') as f:
            json.dump(plan,f,indent=2);f.flush();os.fsync(f.fileno())
        (d/'metadata/source-archive-inventory.json').write_text(json.dumps(doc,indent=2)+'\n')
    with (d/'metadata/move.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        marker=a/'ARCHIVE_PRODUCTS_MOVED_OR_MOVING'
        if marker.exists():
            if marker.read_text()!=str(d)+'\n':raise ValueError('Archive already moving elsewhere')
        else:
            with marker.open('x') as f:f.write(str(d)+'\n');f.flush();os.fsync(f.fileno())
        for stage in sorted(STAGES|{'comparisons'}):(d/stage).mkdir(exist_ok=True)
        for i,row in enumerate(plan['files'],1):
            src,out=paths(a,d,row)
            if src.exists():
                valid(src,row);out.parent.mkdir(parents=True,exist_ok=True)
                if not out.exists():os.link(src,out,follow_symlinks=False)
                elif not os.path.samefile(src,out):raise ValueError('Destination collision')
                valid(out,row)
                if not os.path.samefile(src,out):raise ValueError('Source changed')
                src.unlink() # only after verified destination; no data block deletion
            else:valid(out,row)
            if i%100==0:print('Moved and verified %d/%d'%(i,len(plan['files'])),flush=True)
        (d/'metadata/SHA256SUMS').write_text(''.join(x['sha256']+'  '+x['destination']+'\n' for x in plan['files']))
        (d/'README.txt').write_text('Working products moved from '+str(a)+'\nOriginal archive is no longer intact; source/config/metadata retained there.\n23 existing runs; RF7/run331 still absent. SHA256 checked, not ROOT/scientific validity.\n')
        (d/'IMPORT_MOVE_VERIFIED').write_text('All selected products moved and SHA256 verified. Original archive no longer intact.\n')
        (d/'INCOMPLETE').unlink()
        print('Move verified:',d)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',required=True,type=Path);p.add_argument('--destination',required=True,type=Path);p.add_argument('--plan-sha256',required=True);p.add_argument('--accept-archive-incomplete',action='store_true');p.add_argument('--resume',action='store_true');a=p.parse_args()
    if not a.accept_archive_incomplete:raise ValueError('Requires --accept-archive-incomplete')
    execute(a.archive,a.destination,a.plan_sha256,a.resume)
if __name__=='__main__':
    try:main()
    except Exception as e:print('STOP:',e,file=sys.stderr);sys.exit(1)
