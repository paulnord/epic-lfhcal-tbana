#!/usr/bin/env python3
"""Preview or quarantine interrupted Ari outputs. Never submits or deletes jobs/files.

Run on the normal BNL submission host. Default: preview only.
Use --quarantine to move partial products aside and verify ordinary resume.
Keep the printed quarantine directory and its journal until recovery is reviewed.
"""
import argparse
from collections import Counter
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import tempfile

BASE = Path('/gpfs01/star/scratch/pnord/ari-rebuild-eX4Mld')
EXPECTED = {'rf': {'completed': 133, 'failed': 6, 'pending': 5},
            'other': {'completed': 85, 'failed': 5, 'pending': 10}}
EXPECTED_FAILED = {
    'rf': {'refine3-328-329-2', 'calibrate-303-304-1', 'calibrate-334-335-2',
           'calibrate-336-337-2', 'waveform-296-298-1', 'waveform-299-300-1'},
    'other': {'refine1-348-349-2', 'refine1-358-359-2', 'calibrate-352-353-2',
              'calibrate-362-363-2', 'waveform-346-347-2'}}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(args):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(' '.join(args) + '\n' + result.stdout + result.stderr)
    return result.stdout


def inside(path, root):
    return path == root or root in path.parents


def overlap(a, b):
    return inside(a, b) or inside(b, a)


def exists(path):
    return path.exists() or path.is_symlink()


def fingerprint(path):
    st = path.lstat()
    return [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns]


@contextmanager
def campaign_lock(campaign):
    lock = campaign / 'state' / 'resume.lock'
    lock.mkdir()  # Deliberately refuses any existing lock; never remove a stale one blindly.
    try:
        (lock / 'owner.json').write_text(json.dumps({
            'pid': os.getpid(), 'hostname': socket.gethostname(),
            'purpose': 'reversible interrupted-output quarantine'}))
        yield
    finally:
        (lock / 'owner.json').unlink()
        lock.rmdir()


def snapshot(base):
    campaigns = []
    for tag in ('rf', 'other'):
        c = Path((base / (tag + '-campaign.txt')).read_text().strip())
        require(c.is_absolute() and inside(c.resolve(), (base / 'campaigns').resolve()),
                'Unexpected campaign path: ' + str(c))
        status = json.loads(run(['yall-run', 'status', str(c), '--json']))
        scheduler = status.get('scheduler') or {}
        require(scheduler.get('query_ok') is True, 'Scheduler query is not confirmed successful')
        require(not scheduler.get('active_jobs'), 'Campaign has active jobs: ' + str(c))
        states = {t['name']: t['state'] for t in status['tasks']}
        require(dict(Counter(states.values())) == EXPECTED[tag],
                'Task counts changed; inspect status before recovery: ' + tag)
        require({n for n, s in states.items() if s == 'failed'} == EXPECTED_FAILED[tag],
                'Failed task names changed: ' + tag)
        manifest = json.loads((c / 'campaign.json').read_text())
        tasks = manifest['tasks']
        require(isinstance(tasks, dict) and set(tasks) == set(states), 'Unexpected task schema')
        require(not list((c / 'amendments').glob('*')), 'Campaign has amendments; review first')
        require(not list((c / 'resumes').glob('*')), 'Campaign was already resumed; review first')
        campaigns.append((tag, c, tasks, states))
    return campaigns


def plan(base, campaigns):
    protected = []
    candidates = set()
    for tag, c, tasks, states in campaigns:
        root = (base / tag / 'products').resolve()
        produced = {Path(ref['path']).resolve() for name, task in tasks.items()
                    if states[name] != 'completed' for ref in task.get('outputs', [])}
        for name, task in tasks.items():
            if states[name] == 'completed':
                for ref in task.get('outputs', []):
                    p = Path(ref['path'])
                    require(p.exists(), 'Completed output is missing: ' + str(p))
                    protected.append(p.resolve())
                protected.extend(Path(ref['path']).resolve() for ref in task.get('inputs', []))
                continue
            for ref in task.get('inputs', []):
                require(isinstance(ref['path'], str), 'Unexpected input schema')
                p = Path(ref['path']).resolve()
                if p not in produced:
                    protected.append(p)
            paths = {Path(ref['path']) for ref in task.get('outputs', [])}
            # DataPrep may also emit these native companions after processing;
            # calibration tasks do not declare them in this archived graph.
            if name.startswith('calibrate-'):
                for ref in task.get('outputs', []):
                    if ref['role'] == 'root':
                        p = Path(ref['path'])
                        paths.update(p.with_name(p.stem + suffix)
                                     for suffix in ('_Hists.root', '_calib.txt'))
            argv = task['command']
            argv = shlex.split(argv) if isinstance(argv, str) else argv
            # HGCROCStudy's -o ROOT is a real output but is not declared in the DAG.
            # Preserve it as well as its declared histogram/plots outputs.
            if name.startswith('waveform-'):
                require(argv.count('-o') == 1, 'Unexpected waveform command: ' + name)
                output = Path(argv[argv.index('-o') + 1])
                run_number = name.split('-')[2]
                expected = base / tag / 'products' / 'waveform' / (
                    'calibratedHGCROC_wave_Run_' + run_number + '.root')
                require(output == expected, 'Unexpected waveform output: ' + str(output))
                paths.add(output)
            for p in paths:
                require(p.is_absolute() and inside(p, base / tag / 'products')
                        and inside(p.resolve(), root),
                        'Output is outside this recovery workspace: ' + str(p))
                for parent in [p] + list(p.parents):
                    if parent == base:
                        break
                    require(not parent.is_symlink(), 'Output symlink requires manual review: ' + str(parent))
                if exists(p):
                    candidates.add(p)
    ordered = sorted(candidates, key=lambda p: (len(p.parts), str(p)))
    moves = []
    for p in ordered:
        require(not any(overlap(p.resolve(), q) for q in protected),
                'Partial output overlaps completed output: ' + str(p))
        if not any(inside(p, q) for q in moves):
            moves.append(p)
    return moves


def write_journal(directory, data):
    tmp = directory / '.journal.tmp'
    with tmp.open('w') as handle:
        handle.write(json.dumps(data, indent=2) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(directory / 'journal.json')
    fd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--quarantine', action='store_true', help='move partial outputs aside; no submission')
    args = ap.parse_args()
    base = BASE
    require(base.is_dir(), 'Recovery base not found: ' + str(base))
    print(run(['yall-run', '--version']).strip(), flush=True)
    campaigns = snapshot(base)
    moves = plan(base, campaigns)
    # Read-only preflight: checks Rescue DAG DONE nodes against completed tasks.
    # This is NOT an endorsement of using --overwrite for real submission.
    for tag, c, tasks, states in campaigns:
        print(run(['yall-run', 'resume', str(c), '--dry-run', '--overwrite']).strip(), flush=True)
    print('Preserve 218 completed tasks; continue 26 unfinished tasks.', flush=True)
    print('Partial output paths to quarantine: ' + str(len(moves)), flush=True)
    for p in moves:
        print('  ' + str(p.relative_to(base)), flush=True)
    if not args.quarantine:
        print('PREVIEW ONLY. Nothing moved or submitted.', flush=True)
        return
    require(moves, 'No partial outputs found; inspect before changing anything')
    # Recheck scheduler and states immediately before moving products.
    q = None
    try:
        with ExitStack() as locks:
            for tag, c, tasks, states in campaigns:
                locks.enter_context(campaign_lock(c))
            again = snapshot(base)
            require(again == campaigns and plan(base, again) == moves,
                    'Recovery plan changed; nothing moved')
            stamps = {str(p): fingerprint(p) for p in moves}
            q = Path(tempfile.mkdtemp(prefix='interrupted-products-', dir=str(base)))
            journal = {'base': str(base), 'phase': 'moving', 'moves': [
                {'source': str(p), 'saved': str(q / p.relative_to(base)),
                 'fingerprint': stamps[str(p)], 'moved': False} for p in moves]}
            write_journal(q, journal)
            print('QUARANTINE: ' + str(q), flush=True)
            for tag, c, tasks, states in campaigns:
                evidence = q / 'evidence' / tag
                evidence.mkdir(parents=True)
                for name in ('campaign.json', 'start.json'):
                    shutil.copy2(str(c / name), str(evidence / name))
                shutil.copytree(str(c / 'state'), str(evidence / 'state'),
                                ignore=shutil.ignore_patterns('resume.lock'))
                for p in (c / 'condor').glob('campaign.dag*'):
                    if p.is_file():
                        shutil.copy2(str(p), str(evidence / p.name))
            for item in journal['moves']:
                src, dst = Path(item['source']), Path(item['saved'])
                require(fingerprint(src) == item['fingerprint'], 'Output changed: ' + str(src))
                require(not exists(dst), 'Quarantine destination exists: ' + str(dst))
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.rename(str(src), str(dst))
                item['moved'] = True
                write_journal(q, journal)
            journal['phase'] = 'quarantined'
            write_journal(q, journal)
        # Native resume needs its own lock; release ours before its dry runs.
        for tag, c, tasks, states in campaigns:
            print(run(['yall-run', 'resume', str(c), '--dry-run']).strip(), flush=True)
        journal['phase'] = 'ready_to_resume'
        write_journal(q, journal)
        print('READY TO RESUME. No jobs submitted. Keep this quarantine and journal.', flush=True)
    except BaseException:
        print('STOPPED. No automatic rollback or submission. Quarantine: ' + str(q), flush=True)
        raise


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        raise SystemExit('STOP: ' + str(error))
