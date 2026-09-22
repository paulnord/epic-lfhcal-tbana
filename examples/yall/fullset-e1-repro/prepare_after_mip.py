#!/usr/bin/env python3
"""Prepare a fresh E1 skim comparison using existing adaptive MIP events."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

MIP = 'rawHGCROC_wPedwMuon_wBC_Muon_FullSetE_1'
SELECTED = 'rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_FullSetE_1.root'
FINAL = 'calib_Final_Muon_FullSetE_1_calib.txt'


def prepare(previous, work):
    previous, work = Path(previous).resolve(), Path(work).resolve()
    result = work / 'fullset-e1-repro'
    manifest = work / 'after-mip-setup.json'
    if previous == work or previous in work.parents or work in previous.parents:
        raise ValueError('Previous and new work directories must be separate')
    if result.exists() or result.is_symlink() or manifest.exists():
        raise ValueError('Choose a fresh LFHCAL_WORK; this one was already prepared or used')
    inputs = [previous/'mip'/f'{MIP}.root', previous/'selected'/SELECTED,
              previous/'mip'/f'{MIP}_calib.txt', previous/'mip'/f'{MIP}_Hists.root',
              previous/'final'/FINAL]
    for path in inputs:
        if not path.is_file() or not os.access(path, os.R_OK) or path.stat().st_size == 0:
            raise ValueError(f'Missing, empty or unreadable previous result: {path}')
    # Validate every input before creating output directories or copying files.
    for stage in ('mip', 'selected', 'final', 'baseline', 'skim-check',
                  'refine1', 'refine2', 'refine3', 'refine4', 'refine5'):
        (result/stage).mkdir(parents=True, exist_ok=False)
    for n in range(1, 6):
        (result/'plots'/f'refine{n}').mkdir(parents=True, exist_ok=False)
    (work/'campaigns').mkdir(exist_ok=True)
    copied = []
    for source, target in ((inputs[2], result/'mip'/inputs[2].name),
                           (inputs[3], result/'mip'/inputs[3].name),
                           (inputs[4], result/'baseline'/FINAL)):
        shutil.copy2(source, target)
        copied.append({'source': str(source), 'target': str(target),
                       'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    with manifest.open('x') as stream:
        json.dump({'recipe': 'Yallfile.after-mip', 'previous': str(previous),
                   'work': str(work), 'inputs': [{'path': str(p), 'size_bytes': p.stat().st_size,
                                                'mtime_ns': p.stat().st_mtime_ns} for p in inputs],
                   'copied': copied,
                   'check': 'Host readability/nonzero size. ROOT contents checked by jobs; event trees not copied.'},
                  stream, indent=2)
        stream.write('\n')
    return result


def main():
    try:
        for name in ('LFHCAL_PREVIOUS', 'LFHCAL_WORK'):
            if not os.environ.get(name):
                raise ValueError(f'Set {name} first')
        result = prepare(os.environ['LFHCAL_PREVIOUS'], os.environ['LFHCAL_WORK'])
    except (ValueError, OSError) as error:
        print(f'After-MIP setup failed: {error}', file=sys.stderr)
        return 1
    print(f'Prepared: {result}')
    print('Reusing the pre-skim MIP event file; six analysis jobs, no batch setup job.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
