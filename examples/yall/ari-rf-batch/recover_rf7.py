#!/usr/bin/env python3
"""Prepare RF7 (pedestal 330, signal 331) in a fresh persistent BNL workspace.

Standalone download helper. Heavy processing runs only via Condor; --submit
explicitly submits once. Failed workspaces are retained, never overwritten.
"""
import argparse
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tempfile

SOURCE = '639f59189347169f7c357b784cd99a5fd9922801'
REPOSITORY = 'https://github.com/paulnord/epic-lfhcal-tbana.git'
DEFAULT_PARENT = '/gpfs01/star/pwg/pnord/eic/2026TBdata/analyzed'
DEFAULT_RAW = '/gpfs01/star/pwg/pnord/eic/2026TBdata/raw'
DEFAULT_EIC = '/star/u/pnord/bin/eic-shell'


def check_inputs(parent, raw, eic):
    for path in (parent, raw, eic):
        if not path.is_absolute() or re.search(r'[^A-Za-z0-9_/.-]', str(path)):
            raise ValueError('Use absolute shared-storage paths with no spaces: ' + str(path))
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise ValueError('Archive parent is not a writable directory: ' + str(parent))
    for run in (330, 331):
        path = raw / f'Run{run}.h2g'
        if not path.is_file() or not os.access(path, os.R_OK) or path.stat().st_size == 0:
            raise ValueError('Missing, unreadable or empty raw input: ' + str(path))
    if not eic.is_file() or not os.access(eic, os.X_OK):
        raise ValueError('Missing executable EIC launcher: ' + str(eic))
    for command in ('git', 'yall-run', 'condor_submit', 'condor_submit_dag'):
        if not shutil.which(command):
            raise ValueError('Required host command not found: ' + command)


def run(command, cwd=None, capture=False):
    print('+ ' + ' '.join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), cwd=cwd, check=True,
                          text=True, stdout=subprocess.PIPE if capture else None)


def recover(parent, raw, eic, submit=False):
    check_inputs(parent, raw, eic)
    # Do not resolve /gpfs01 into submit-host-only /gpfs/mnt aliases.
    base = Path(tempfile.mkdtemp(prefix='ari-rf7-', dir=str(parent)))
    print('Persistent workspace: ' + str(base), flush=True)
    source, work = base / 'source', base / 'work'
    run(['git', 'clone', '--no-checkout', REPOSITORY, source])
    run(['git', '-C', source, 'checkout', '--detach', SOURCE])
    actual = run(['git', '-C', source, 'rev-parse', 'HEAD'], capture=True).stdout.strip()
    if actual != SOURCE:
        raise ValueError('Unexpected checkout SHA; no campaign created')
    run(['git', '-C', source, 'submodule', 'update', '--init', '--recursive'])
    preparation = runpy.run_path(str(source / 'examples/yall/ari-rf-batch/prepare.py'))
    preparation['prepare'](work, raw, eic, 'full', True,
                           pairs_override=[(330, 331, 2)],
                           campaign_name='ari-rf7-run331')
    run(['yall-run', 'validate'], cwd=work)
    plan = run(['yall-run', 'plan'], cwd=work, capture=True).stdout
    (work / 'plan.txt').write_text(plan)
    print(plan, flush=True)
    if not submit:
        print('Prepared only. To submit from tcsh:\ncd ' + str(work) +
              '\nset C = `yall-run create --campaigns-dir ' + str(base / 'campaigns') +
              '`\nyall-run start "$C"\nyall-run status "$C"')
        return base
    campaign = run(['yall-run', 'create', '--campaigns-dir', base / 'campaigns'],
                   cwd=work, capture=True).stdout.strip()
    if not campaign or '\n' in campaign:
        raise ValueError('Unexpected campaign path output; inspect workspace before any retry')
    (work / 'campaign-path.txt').write_text(campaign + '\n')
    print('Campaign: ' + campaign, flush=True)
    # Never retry an uncertain scheduler submission automatically.
    run(['yall-run', 'start', campaign], cwd=work)
    run(['yall-run', 'status', campaign], cwd=work)
    print('Submitted, not completed. Keep this entire workspace; do not move it while running.')
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, default=Path(DEFAULT_PARENT))
    parser.add_argument('--raw', type=Path, default=Path(DEFAULT_RAW))
    parser.add_argument('--eic-shell', type=Path, default=Path(DEFAULT_EIC))
    parser.add_argument('--submit', action='store_true', help='submit once after preparation and validation')
    args = parser.parse_args()
    try:
        recover(args.parent, args.raw, args.eic_shell, args.submit)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, 'RF7 stopped: ' + str(exc) + '\nExisting files retained; inspect before retrying.\n')


if __name__ == '__main__':
    main()
