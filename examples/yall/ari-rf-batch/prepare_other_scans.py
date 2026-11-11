#!/usr/bin/env python3
"""Prepare nine recorded SPS CC/CF/CFComp runs; never submit or pool them by RF."""
import argparse
import csv
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location('ari_prepare', Path(__file__).with_name('prepare.py'))
p = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p)
# Historical calibration Set3 explicitly selects ParamScan_2.csv.
PAIRS = [(ped, ped+1, 2) for ped in range(346, 363, 2)]
SETTINGS = {347:(9,7,4,1),349:(9,7,8,1),351:(9,7,10,1),353:(9,7,1,1),
            355:(9,5,5,1),357:(9,5,5,8),359:(9,5,5,15),361:(9,3,5,1),363:(9,5,5,1)}
SCANS = {
    'CC': {'runs':[353,347,298,349,351], 'fixed':{'RF':9,'CF':7,'CFComp':1}},
    'CF': {'runs':[361,355,363,298], 'fixed':{'RF':9,'CC':5,'CFComp':1}},
    'CFComp': {'runs':[355,357,359], 'fixed':{'RF':9,'CF':5,'CC':5}},
}

def prepare(destination, raw, eic_shell, acknowledge, baseline_workspace=None):
    db = p.REPO/'configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv'
    with db.open() as f:
        for _ in range(5): next(f)
        rows = {int(r['Run Number']):r for r in csv.DictReader(f) if r['Run Number'].isdigit()}
    names = ('RF','CF','CC','CFComp')
    for ped, run, scan in PAIRS:
        for n in (ped,run):
            if tuple(int(rows[n][k]) for k in names) != SETTINGS[run]:
                raise ValueError(f'Run database settings mismatch for run {n}')
        if rows[ped]['beam species'] != 'pedestal' or rows[run]['beam species'] != 'Muon +':
            raise ValueError(f'Run database pedestal/signal identity mismatch: {ped}/{run}')
    if tuple(int(rows[298][k]) for k in names) != (9,7,5,1):
        raise ValueError('RF baseline run298 settings mismatch')
    if not (p.REPO/'configs/TB2026/ToAOffsets_TBSPS2026_ParamScan_2.csv').is_file():
        raise ValueError('Missing historical Set3 ToA file ParamScan_2.csv')
    manifest = {'scans':SCANS, 'run_settings':{str(r):dict(zip(names,v)) for r,v in SETTINGS.items()},
        'RF_resistance_kOhm':80/9, 'ToA_provenance':'runHGCROCCalibration_TBSPSH2_2026.sh calibMuonParScan Set3 selects ParamScan_2.csv',
        'comparison_note':'No RF-only summary: all nine runs have RF9 but different CF/CC/CFComp. Run355 is processed once and reused in CF and CFComp comparisons. Runs355/363 are distinct repeated CF5 acquisitions.',
        'baseline_run':298,'baseline_settings':dict(zip(names,(9,7,5,1))),
        'baseline_note':'Existing RF run298 is a reference only; not consumed, modified, or reprocessed by this graph.'}
    if baseline_workspace is not None:
        if not baseline_workspace.is_absolute(): raise ValueError('Baseline workspace must be absolute')
        manifest['baseline_reference_only'] = {
            'workspace':str(baseline_workspace),
            'calibrated':str(baseline_workspace/'products/calibrated/calibratedHGCROC_Run_298.root'),
            'waveform':str(baseline_workspace/'products/waveform/calibratedHGCROC_wave_Run_298_Hists.root')}
    p.prepare(destination,raw,eic_shell,'other-settings',acknowledge,pairs_override=PAIRS,
              campaign_name='ari-other-settings',include_summary=False,extra_metadata=manifest)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--eic-shell',type=Path,required=True)
    parser.add_argument('--baseline-workspace',type=Path)
    parser.add_argument('--accept-repo-scan-recipe',action='store_true')
    a=parser.parse_args()
    try: prepare(a.destination,a.raw,a.eic_shell,a.accept_repo_scan_recipe,a.baseline_workspace)
    except (ValueError, OSError, KeyError) as exc: parser.error(str(exc))
