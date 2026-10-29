#!/usr/bin/env python3
"""Prepare, never submit, an isolated Condor RF campaign using repository templates."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess

PAIRS = [(296,298,1),(299,300,1),(303,304,1),(305,306,1),(309,310,1),
         (328,329,2),(332,333,2),(334,335,2),(336,337,2),(338,339,2),
         (340,341,2),(342,343,2),(344,345,2)]
REPO = Path(__file__).resolve().parents[3]

def prepare(destination, raw, eic_shell, mode, acknowledge):
    if not acknowledge:
        raise ValueError('Select --accept-repo-scan-recipe only after reviewing README: review recovered Ari script provenance and current raw/config inputs')
    paths = [destination, raw, eic_shell, REPO]
    if any(not p.is_absolute() or re.search(r'[^A-Za-z0-9_/.-]', str(p)) for p in paths):
        raise ValueError('Use absolute paths containing only letters, digits, underscore, slash, dot, hyphen')
    if destination.exists():
        raise ValueError('Destination already exists; use a new empty campaign workspace')
    pairs = PAIRS[:1] if mode == 'pilot' else PAIRS
    missing = [str(raw / f'Run{r}.h2g') for r in sorted({r for p in pairs for r in p[:2]}) if not (raw / f'Run{r}.h2g').is_file() or not os.access(raw / f'Run{r}.h2g', os.R_OK) or (raw / f'Run{r}.h2g').stat().st_size == 0]
    if missing:
        raise ValueError('Missing, unreadable or empty raw inputs: ' + ', '.join(missing))
    if not eic_shell.is_file() or not os.access(eic_shell, os.X_OK):
        raise ValueError('Missing worker-visible EIC_SHELL: ' + str(eic_shell))
    template = (REPO/'examples/yall/scan-set-1/Yallfile').read_text()
    template = template.replace('campaign lfhcal-tb2026-scan-set-1', f'campaign ari-rf-{mode}')
    template = template.replace('@env LFHCAL_DATA', f'@set LFHCAL_DATA {raw}')
    template = template.replace('@env LFHCAL_WORK', f'@set LFHCAL_WORK {destination}')
    template = template.replace('@env EIC_SHELL', f'@set EIC_SHELL {eic_shell}')
    template = template.replace('@set BUILD ../../../NewStructure/build', f'@set BUILD {destination}/build')
    template = template.replace('../../../configs/TB2026', f'{REPO}/configs/TB2026')
    template = re.sub(r'@set TOA .*\n', '', template)
    template = template.replace('@input toa {TOA}', '@input toa {TB2026_CONFIG}/ToAOffsets_TBSPS2026_ParamScan_{scan}.csv')
    template = template.replace('../../../tools/run-in-eic-shell.sh', str(REPO/'examples/yall/ari-rf-batch/worker.sh'))
    # No automatic retries: failed outputs require operator review.
    template = re.sub(r'@table pairs ped run:\n(?:    \d+ \d+\n)+', '@table pairs ped run scan:\n' + ''.join(f'    {p} {r} {s}\n' for p,r,s in pairs), template)
    # Carry scan identity with pair-derived stages; single-column conversion and pedestal stay deduplicated.
    template = template.replace('{ped}-{run}', '{ped}-{run}-{scan}')
    template = template.replace('@each ped run in pairs', '@each ped run scan in pairs')
    template = template.replace('convert-{run}:\n', 'convert-{run}: build\n')
    template = template.replace('scan-set-1/', 'products/')
    # All heavy work, including compilation and tests, executes as Condor nodes.
    build = f'''build:
    @input driver {REPO}/examples/yall/ari-rf-batch/build.sh
    @output ready {destination}/build/READY
    %cpus 2
    %memory 4GB
    %disk 8GB
    /bin/bash @input.driver {REPO} {destination}/build @output.ready

'''
    template = template.replace('# Convert every unique run once;', build + '# Convert every unique run once;')
    # Declarative fan-in collects all calibrated and waveform files, never an untracked glob.
    template += f'''\nsummary: waveform-{{ped}}-{{run}}-{{scan}}
    @input calibrated {{LFHCAL_WORK}}/products/calibrated/calibratedHGCROC_Run_{{run}}.root
    @input hists {{LFHCAL_WORK}}/products/waveform/calibratedHGCROC_wave_Run_{{run}}_Hists.root
    @input rundb {{TB2026_CONFIG}}/DataTakingDB_TBSPSH2_202605_HGCROC.csv
    @input driver {REPO}/examples/yall/ari-rf-batch/compare.py
    @output root {{LFHCAL_WORK}}/ari_rf_comparison.root
    @output plots {{LFHCAL_WORK}}/ari_rf_plots
    python3 @input.driver {{BUILD}}/CompareWaveform @input.rundb @output.root @output.plots --calibrated @input.calibrated --hists @input.hists
'''
    template = re.sub(r'(^[^#@% \n][^\n]*:\s*[^\n]*\n)', r'\1    %retry 0\n', template, flags=re.MULTILINE)
    destination.mkdir(parents=True)
    (destination/'Yallfile').write_text(template)
    tracked = list((REPO/'configs/TB2026').glob('*')) + list(Path(__file__).parent.glob('*.py')) + list(Path(__file__).parent.glob('*.sh')) + [REPO/'tools/run-in-eic-shell.sh', REPO/'examples/yall/scan-set-1/Yallfile']
    hashes = {str(f.relative_to(REPO)):hashlib.sha256(f.read_bytes()).hexdigest() for f in tracked if f.is_file()}
    raw_stats = {str(raw/f'Run{r}.h2g'):{'size':(raw/f'Run{r}.h2g').stat().st_size,'mtime_ns':(raw/f'Run{r}.h2g').stat().st_mtime_ns} for r in sorted({r for p in pairs for r in p[:2]})}
    metadata = {'input_sha256':hashes, 'raw_stat_not_hash':raw_stats, 'git_diff':subprocess.check_output(['git','-C',str(REPO),'diff','HEAD'],text=True), 'mode':mode, 'recipe':'recovered Ari reduced-tree three-pass/fullMuon sequence; existing scan-set-1 template', 'pairs':pairs,
                'repo':str(REPO), 'commit':subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
                'raw':str(raw),'eic_shell':str(eic_shell), 'event_limit':None,
                'note':'Pilot uses one complete run and its pedestal; this is not a 1000-event calibration.'}
    (destination/'preparation.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(destination)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--eic-shell',type=Path,required=True)
    parser.add_argument('--mode',choices=['pilot','full'],required=True)
    parser.add_argument('--accept-repo-scan-recipe',action='store_true')
    args=parser.parse_args()
    try: prepare(args.destination,args.raw,args.eic_shell,args.mode,args.accept_repo_scan_recipe)
    except ValueError as exc: parser.error(str(exc))
