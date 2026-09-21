#!/usr/bin/env python3
"""Create fresh FullSetE_1 directories and check converted inputs on the host."""
import json
import os
from pathlib import Path
import sys

STAGES = ('converted', 'pedestal', 'transfer', 'mip', 'selected',
          'refine1', 'refine2', 'refine3', 'refine4', 'refine5', 'final')
PLOTS = ('pedestal', 'transfer', 'mip', 'refine1', 'refine2',
         'refine3', 'refine4', 'refine5')


def prepare(converted, work):
    converted, work = Path(converted).resolve(), Path(work).resolve()
    result = work / 'fullset-e1-repro'
    manifest = work / 'host-setup.json'
    if work == converted or converted in work.parents:
        raise ValueError('LFHCAL_WORK must be outside the converted-input directory')
    if result.exists() or result.is_symlink() or manifest.exists():
        raise ValueError('This work directory was already prepared or used; choose a fresh LFHCAL_WORK')
    inputs = []
    for run in range(372, 379):
        path = converted / f'rawHGCROC_{run}.root'
        if not path.is_file() or not os.access(path, os.R_OK) or path.stat().st_size == 0:
            raise ValueError(f'Missing, empty or unreadable converted input: {path}')
        inputs.append({'run': run, 'path': str(path), 'size_bytes': path.stat().st_size})
    # All input checks finish before creating any directories.
    for stage in STAGES:
        (result / stage).mkdir(parents=True, exist_ok=True)
    for stage in PLOTS:
        (result / 'plots' / stage).mkdir(parents=True, exist_ok=True)
    (work / 'campaigns').mkdir(exist_ok=True)
    with manifest.open('x') as stream:
        json.dump({'recipe': 'Yallfile.test-host-setup', 'work': str(work),
                   'inputs': inputs, 'check': 'Host readability and nonzero size; no ROOT validation'},
                  stream, indent=2)
        stream.write('\n')
    return result


def main():
    try:
        for key in ('LFHCAL_CONVERTED', 'LFHCAL_WORK'):
            if not os.environ.get(key):
                raise ValueError(f'Set {key} first')
        result = prepare(os.environ['LFHCAL_CONVERTED'], os.environ['LFHCAL_WORK'])
    except (OSError, ValueError) as error:
        print(f'Host setup failed: {error}', file=sys.stderr)
        return 1
    print(f'Host setup complete: {result}')
    print('Seven converted inputs checked; no batch job submitted.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
