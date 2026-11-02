#!/usr/bin/env python3
"""Prepare one isolated Condor plot job after both waveform campaigns finish."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
REPO=Path(__file__).resolve().parents[3]
_spec=importlib.util.spec_from_file_location('all_scans',Path(__file__).with_name('plot_all_scans.py'))
plots=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(plots)


def prepare(destination,rf,other,eic,run302=None,rf_diagnostics=False):
    for p in (destination,rf,other,eic,REPO,*([run302] if run302 else [])):
        if not p.is_absolute() or re.search(r'[^A-Za-z0-9_/.-]',str(p)):
            raise ValueError('Use absolute paths with only letters, digits, underscore, slash, dot, hyphen')
    if destination.exists():raise ValueError('Destination exists; use a fresh directory')
    if any(p.resolve()==destination.resolve() or p.resolve() in destination.resolve().parents for p in (rf,other)):
        raise ValueError('Plot destination must be outside both input workspaces')
    if not eic.is_file() or not os.access(eic,os.X_OK):raise ValueError('EIC launcher is not executable')
    inputs=[]
    paths=plots.input_paths(rf,other,run302)
    groups=plots.scan_groups(paths)
    for run,p in paths.items():
        if not p.is_file() or not os.access(p,os.R_OK) or p.stat().st_size<=0:
            raise ValueError(f'Missing/empty waveform result; wait for both campaigns to finish: {p}')
        st=p.stat();inputs.append({'run':run,'path':str(p),'size_bytes':st.st_size,'mtime_ns':st.st_mtime_ns})
    script=REPO/'examples/yall/ari-rf-batch/plot_all_scans.py';wrapper=script.with_name('worker.sh')
    rundb=REPO/'configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv'
    plots.read_settings(rundb)
    extra=[]
    if rf_diagnostics:
        extra=[('summary',script.with_name('root_rf_summary.py')),
               ('channels',script.with_name('root_rf_channels.py')),
               ('mapping',REPO/'configs/TB2026/mapping_HGCROC_SPSH2TB_sumV2_default.csv')]
        for _,path in extra:
            if not path.is_file(): raise ValueError(f'Missing diagnostic source: {path}')
    source=f'''campaign ari-all-scans-plots
backend condor
%account-provenance off
%cpus 1
%memory 2GB
%disk 2GB
%time 30m
%getenv true
%wrapper {wrapper} {eic} /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1

plots:
    @input driver {script}
    @input rundb {rundb}
    @input provenance {destination}/preparation.json
'''
    source+=''.join(f"    @input waveform {item['path']}\n" for item in inputs)
    source+=''.join(f'    @input {alias} {path}\n' for alias,path in extra)
    options=' --rf-diagnostics --summary-module @input.summary --channel-module @input.channels --mapping @input.mapping' if rf_diagnostics else ''
    source+=f'''    @output results {destination}/results
    python3 @input.driver --rf-workspace {rf} --other-workspace {other} --rundb @input.rundb --input-manifest @input.provenance --output @output.results{options}
'''
    tracked=[Path(__file__).resolve(),script,wrapper,rundb,*[path for _,path in extra]]
    metadata={'repo':str(REPO),'commit':subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),'git_diff':subprocess.check_output(['git','-C',str(REPO),'diff','HEAD'],text=True),'code_sha256':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked},'inputs':inputs,'rf_workspace':str(rf),'other_workspace':str(other),'groups':groups,'rf_diagnostics':rf_diagnostics,'note':'One plot-only worker; no fits, event processing, input mutation or submission. Inputs must be completed immutable waveform results. Run302 included only when an existing result is present/provided.'}
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.ari-all-scans-',dir=destination.parent))
    try:
        (staging/'Yallfile').write_text(source);(staging/'preparation.json').write_text(json.dumps(metadata,indent=2)+'\n')
        from yall_run.model import load_spec
        spec=load_spec(staging/'Yallfile')
        if len(spec.tasks)!=1 or len(spec.tasks[0].inputs)!=len(inputs)+3+len(extra):
            raise ValueError('Unexpected plot graph input count')
        if destination.exists():raise ValueError('Destination appeared during preparation')
        staging.rename(destination)
    finally:
        if staging.exists():shutil.rmtree(staging)
    print(destination)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination',type=Path,required=True);p.add_argument('--rf-workspace',type=Path,required=True)
    p.add_argument('--other-workspace',type=Path,required=True);p.add_argument('--eic-shell',type=Path,required=True)
    p.add_argument('--run302-input',type=Path,help='Existing run302 waveform histogram file outside the RF workspace')
    p.add_argument('--rf-diagnostics',action='store_true',help='Add native ROOT resistance summaries and channel maps/comparisons')
    a=p.parse_args()
    try:prepare(a.destination,a.rf_workspace,a.other_workspace,a.eic_shell,a.run302_input,a.rf_diagnostics)
    except (ValueError,OSError) as e:p.error(str(e))
