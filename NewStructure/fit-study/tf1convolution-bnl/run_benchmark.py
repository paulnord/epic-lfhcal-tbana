#!/usr/bin/env python3
"""Supervise independent ROOT workers; preserve completed and timed-out attempts.

The supervisor never imports ROOT. A fresh executable process handles each
(cell, method, repetition). Timeouts therefore work even inside unresponsive
C++ code; no Python signal callback or thread is asked to interrupt ROOT.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

import benchmark as b


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def stop_worker(proc):
    """Kill only this worker's process group, not other user jobs."""
    if proc.poll() is not None:
        return
    def send(sig):
        try:
            if os.name == 'posix':
                os.killpg(proc.pid, sig)
            elif sig == signal.SIGTERM:
                proc.terminate()
            else:
                proc.kill()
        except ProcessLookupError:
            pass
    send(signal.SIGTERM)
    try:
        proc.wait(timeout=2.)
    except subprocess.TimeoutExpired:
        send(signal.SIGKILL)
        proc.wait()


def run_worker(command, directory, log_path, limits, total_limit,
               heartbeat=10., poll=.2):
    """Enforce cumulative time in each phase, plus a whole-worker bound.

    Phase timing includes phase-local setup and checkpoint writes. It is not a
    replacement for the fit's separately measured CPU/wall time.
    """
    start = time.monotonic()
    spent = {k:0. for k in limits}
    phase, stage = 'startup', 'starting process'
    seen = None
    last, next_heartbeat = start, start+heartbeat
    print(f'START {log_path.stem}',flush=True)
    with log_path.open('w') as log:
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=(os.name=='posix'))
        try:
            while proc.poll() is None:
                now = time.monotonic()
                spent[phase] += now-last
                last = now
                state = read_json(directory/'progress.json',{})
                event = state.get('monotonic_s')
                if event is not None and event != seen:
                    seen = event
                    stage = state.get('stage','unknown')
                    next_phase = state.get('phase','startup')
                    phase = next_phase if next_phase in limits else 'startup'
                    print(f'  {log_path.stem}: {stage} (pid {proc.pid})',flush=True)
                elapsed = now-start
                expired = spent[phase] >= limits[phase] or elapsed >= total_limit
                if expired:
                    stop_worker(proc)
                    result = dict(outcome='timeout',timeout_phase=phase,
                        timeout_stage=stage,worker_wall_s=time.monotonic()-start,
                        timeout_limit_s=limits[phase],phase_elapsed_s=spent[phase],
                        worker_returncode=proc.returncode,worker_pid=proc.pid,
                        log_path=str(log_path))
                    b.write_json(directory.parent/(directory.name+'-watchdog.json'),result)
                    print(f'  TIMEOUT in {stage}; worker stopped, continuing. Log: {log_path}',flush=True)
                    return result
                if now >= next_heartbeat:
                    print(f'  alive {log_path.stem}: {stage}; {spent[phase]:.0f}/{limits[phase]:g}s in {phase}',flush=True)
                    next_heartbeat = now+heartbeat
                time.sleep(poll)
        except BaseException:
            stop_worker(proc)
            raise
    return dict(outcome='completed' if proc.returncode==0 else 'crash',
                worker_returncode=proc.returncode,worker_wall_s=time.monotonic()-start,
                worker_pid=proc.pid,log_path=str(log_path))


def positive(text):
    value = float(text)
    if not math.isfinite(value) or value<=0:
        raise argparse.ArgumentTypeError('must be finite and positive')
    return value


def completed_rows(path):
    if not path.is_file():
        return []
    with path.open(newline='') as handle:
        return list(csv.DictReader(handle))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--preset',choices=('smoke','survey'),default='smoke')
    ap.add_argument('--datasets',nargs='+',choices=b.SETS)
    ap.add_argument('--cells',nargs='+',type=int)
    ap.add_argument('--methods',nargs='+',choices=[m[0] for m in b.METHODS])
    ap.add_argument('--repeats',type=int,default=1)
    ap.add_argument('--fit-timeout',type=positive,default=30.)
    ap.add_argument('--check-timeout',type=positive,default=60.)
    ap.add_argument('--startup-timeout',type=positive,default=120.)
    ap.add_argument('--attempt-timeout',type=positive,default=240.)
    args = ap.parse_args()
    if args.repeats<1:
        ap.error('--repeats must be positive')
    out = args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):
        ap.error('Output directory must be empty; preserve earlier attempts')
    logs = out/'logs'
    attempts = out/'attempts'
    logs.mkdir(); attempts.mkdir()
    limits = dict(startup=args.startup_timeout,fit=args.fit_timeout,checks=args.check_timeout)
    here = Path(__file__).resolve().parent
    executable = [sys.executable,'-u',str(here/'benchmark.py')]
    common = ['--work',str(args.work.resolve()),'--preset',args.preset]
    filters = (['--datasets',*args.datasets] if args.datasets else [])
    if args.cells:
        filters += ['--cells',*[str(c) for c in args.cells]]
    check_dir = out/'self-test'
    check = run_worker(executable+['--self-test','--out',str(check_dir)],
                       check_dir,logs/'self-test.log',limits,args.attempt_timeout)
    if check['outcome']!='completed':
        raise SystemExit(f'ROOT self-test failed ({check["outcome"]}); see {logs/"self-test.log"}')
    selection = out/'selection'
    result = run_worker(executable+common+filters+['--prepare-only','--out',str(selection)],
                        selection,logs/'selection.log',limits,args.attempt_timeout)
    manifest = read_json(selection/'manifest.json')
    if result['outcome']!='completed' or not manifest:
        raise SystemExit(f'Selection failed ({result["outcome"]}); see {logs/"selection.log"}')
    methods = [m for m in b.METHODS if not args.methods or m[0] in args.methods]
    manifest['supervision'] = dict(phase_limits_s=limits,attempt_limit_s=args.attempt_timeout,
        methods=methods,repeats=args.repeats,argv=sys.argv,
        supervisor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        timeout_times_are_censored=True,
        separate_process_per='case, method, repetition')
    b.write_json(out/'manifest.json',manifest)
    rows,probes = [],[]
    for case in manifest['cases']:
        for rep in range(args.repeats):
            order = list(methods)
            random.Random(f'{case["case_id"]}:{rep}:20260928').shuffle(order)
            for method in order:
                name = method[0]
                tag = f'{case["dataset"]}-{case["cell"]}-{name}-r{rep}'
                directory = attempts/tag
                command = executable+common+['--datasets',case['dataset'],
                    '--cells',str(case['cell']),'--methods',name,'--repeats','1',
                    '--repeat-offset',str(rep),'--out',str(directory)]
                result = run_worker(command,directory,logs/(tag+'.log'),limits,args.attempt_timeout)
                data = completed_rows(directory/'fits.csv')
                row = (data[0] if data else read_json(directory/'partial-fit.json',{}))
                for key in ('case_id','dataset','cell','category','entries','setup_source'):
                    row[key] = case[key]
                row.update(method=name,repeat=rep)
                # If a fit completed but validation hung, retain the completed
                # fit measurement; never invent a completion time for a killed fit.
                if result['outcome']!='completed':
                    row.update(result)
                    row['error'] = f'{result["outcome"]}: see worker log'
                    if result.get('timeout_phase')=='fit' and row.get('fit_wall_s') in (None,'','?'):
                        row['fit_wall_s'] = None
                        row['fit_time_censored'] = True
                        row['fit_wall_lower_bound_s'] = result['phase_elapsed_s']
                else:
                    row.update({k:v for k,v in result.items() if k!='outcome'})
                    row.setdefault('outcome','error' if not data else 'completed')
                rows.append(row)
                probes.extend(completed_rows(directory/'probes.csv'))
                b.write_csv(out/'fits.csv',rows)
                b.write_csv(out/'probes.csv',probes)
                b.write_json(out/'summary.json',b.summarize(rows))
                print(f'SAVED {tag}: {row["outcome"]}, fit_seconds={row.get("fit_wall_s","?")}',flush=True)
    print(f'Finished. Summary: {out/"summary.json"}',flush=True)


if __name__=='__main__':
    main()
