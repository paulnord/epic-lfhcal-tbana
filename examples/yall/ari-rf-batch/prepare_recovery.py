#!/usr/bin/env python3
"""Prepare an isolated 93-node recovery; never submit or alter the old campaign.

Reuse only successful transfer outputs. ROOT structural checks run in the new
build worker, not on the login host. These checks are not scientific validation.
"""
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

_spec = importlib.util.spec_from_file_location('ari_prepare', Path(__file__).with_name('prepare.py'))
_p = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_p)
REPO = _p.REPO
PAIRS = _p.PAIRS


def read_json(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(path):
    if not path.is_absolute() or re.search(r'[^A-Za-z0-9_/.-]', str(path)):
        raise ValueError('Use absolute paths with only letters, digits, underscore, slash, dot, hyphen')


def prepare(destination, previous, campaign, eic_shell):
    from yall_run.syntax import load_yall_spec
    for path in (destination, previous, campaign, eic_shell, REPO):
        safe_path(path)
    if destination.exists():
        raise ValueError('Destination exists; use a fresh recovery workspace')
    for protected in (previous, campaign):
        if destination.resolve() == protected.resolve() or protected.resolve() in destination.resolve().parents:
            raise ValueError('Recovery destination must be outside the old workspace/campaign')
    if not eic_shell.is_file() or not os.access(eic_shell, os.X_OK):
        raise ValueError('EIC shell launcher is not executable')
    old = read_json(previous/'preparation.json')
    if old.get('mode') != 'full' or old.get('pairs') != [list(p) for p in PAIRS]:
        raise ValueError('Previous preparation must have the exact full 13 pedestal/run/scan pairs')
    manifest = read_json(campaign/'campaign.json')
    archived = campaign/'Yallfile'
    if manifest.get('backend') != 'condor' or manifest.get('spec_archive', {}).get('sha256') != sha(archived):
        raise ValueError('Condor archived recipe hash does not match manifest')
    if sha(previous/'Yallfile') != sha(archived):
        raise ValueError('Previous workspace recipe does not match archived campaign')
    if (campaign/'amendments').exists() and any((campaign/'amendments').iterdir()):
        raise ValueError('Amended campaigns need manual provenance review')
    source = archived.read_text()
    sets = dict(re.findall(r'^@set (\w+) (\S+)$', source, flags=re.M))
    # The CLI records ordinary @set defaults here too, not only overrides.
    # Accept the archived recipe's exact values; never silently reinterpret
    # changed or unrecognized parameters while reconstructing the workflow.
    recorded_sets = manifest.get('set_values') or {}
    if not isinstance(recorded_sets, dict) or any(
        key not in sets or value != sets[key]
        for key, value in recorded_sets.items()
    ):
        raise ValueError('Recorded parameters differ from archived @set values; manual provenance review required')
    if Path(sets.get('LFHCAL_WORK', '/')).resolve() != previous.resolve():
        raise ValueError('Campaign LFHCAL_WORK does not match previous workspace')
    reused = []
    for ped, run, scan in PAIRS:
        name = f'transfer-{ped}-{run}-{scan}'
        task = manifest['tasks'][name]
        state = read_json(campaign/'state'/f'{name}.json')
        number = state.get('attempts')
        if state.get('state') != 'completed' or state.get('last_returncode') != 0 or not isinstance(number, int):
            raise ValueError(f'{name}: latest task state is not completed successfully')
        attempt_path = campaign/f'{name}_attempt_{number:03d}'/'attempt.json'
        attempt = read_json(attempt_path)
        if (attempt.get('task'), attempt.get('attempt'), attempt.get('state'), attempt.get('returncode'), attempt.get('command_returncode')) != (name, number, 'completed', 0, 0):
            raise ValueError(f'{name}: latest attempt is not completed successfully')
        if attempt.get('command') != task.get('command'):
            raise ValueError(f'{name}: completed attempt command differs from frozen task')
        expected = previous/f'products/transfer/rawHGCROC_wPed_wBC_{run}.root'
        declared = [r for r in task['outputs'] if r.get('role') == 'root']
        records = [r for r in attempt['outputs'] if r.get('role') == 'root']
        if len(declared) != 1 or len(records) != 1 or any(Path(r['path']).resolve() != expected.resolve() for r in declared+records):
            raise ValueError(f'{name}: transfer output path mismatch')
        # Check exact paired pedestal and signal inputs, not just a matching filename.
        inputs = {r['role']: Path(r['path']).resolve() for r in task['inputs']}
        if inputs.get('pedestal') != (previous/f'products/pedestal/rawHGCROC_wPed_{ped}.root').resolve() or inputs.get('raw') != (previous/f'products/converted/rawHGCROC_{run}.root').resolve():
            raise ValueError(f'{name}: pedestal/run input mismatch')
        record = records[0]
        stat = expected.stat()
        if not expected.is_file() or not os.access(expected, os.R_OK) or stat.st_size <= 0 or not record.get('exists') or record.get('size_bytes') != stat.st_size or record.get('mtime_ns') != stat.st_mtime_ns:
            raise ValueError(f'{name}: transfer missing, empty, unreadable or changed since successful attempt')
        reused.append({'task': name, 'pedestal':ped, 'run':run, 'scan':scan, 'path':str(expected), 'size_bytes':stat.st_size, 'mtime_ns':stat.st_mtime_ns, 'attempt':number, 'attempt_json':str(attempt_path), 'attempt_sha256':sha(attempt_path), 'command':attempt.get('command')})
    # Preserve archived scientific commands; only remove upstream stages and
    # redirect code/build/new products. No edits to the old recipe or outputs.
    source = re.sub(r'^campaign .*$', 'campaign ari-rf-recovery', source, flags=re.M)
    source = source.replace(old['repo'], str(REPO)).replace(str(sets['LFHCAL_WORK']), str(destination))
    source = re.sub(r'^@set EIC_SHELL .*$', f'@set EIC_SHELL {eic_shell}', source, flags=re.M)
    for stage in ('convert', 'pedestal', 'transfer'):
        source = re.sub(r'^'+stage+r'-[^\n]*\n(?:(?:[ \t].*|)\n)*', '', source, flags=re.M)
    source = source.replace('mip-{ped}-{run}-{scan}: transfer-{ped}-{run}-{scan}', 'mip-{ped}-{run}-{scan}: build\n    @each ped run scan in pairs')
    source = source.replace('@input root {LFHCAL_WORK}/products/transfer/', f'@input root {previous}/products/transfer/')
    build_command = f'    /bin/bash @input.driver {REPO} {destination}/build @output.ready'
    if source.count(build_command) != 1:
        raise ValueError('Unsupported archived build command; refusing ambiguous transformation')
    source = source.replace(build_command, f'    @input recovery {destination}/recovery.json\n    @input verify {REPO}/examples/yall/ari-rf-batch/prepare_recovery.py\n'+build_command.replace('    /bin/bash', '    ! /bin/bash')+' && python3 @input.verify --verify-root @input.recovery')
    metadata = {'previous_workspace':str(previous), 'previous_campaign':str(campaign), 'previous_campaign_id':manifest['id'], 'previous_source_commit':old['commit'], 'previous_preparation_sha256':sha(previous/'preparation.json'), 'previous_manifest_sha256':sha(campaign/'campaign.json'), 'previous_recipe_sha256':sha(archived), 'repo':str(REPO), 'commit':subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(), 'git_diff':subprocess.check_output(['git','-C',str(REPO),'diff','HEAD'],text=True), 'pairs':PAIRS, 'transfers':reused, 'note':'Reuses successful transfer products read-only; fresh build and all downstream outputs. Structural ROOT checks do not establish scientific validity.'}
    metadata['code_sha256'] = {str(p.relative_to(REPO)):sha(p) for p in list((REPO/'examples/yall/ari-rf-batch').glob('*.py'))+list((REPO/'examples/yall/ari-rf-batch').glob('*.sh'))+list((REPO/'configs/TB2026').glob('*')) if p.is_file()}
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.ari-recovery-', dir=destination.parent))
    try:
        (staging/'Yallfile').write_text(source)
        (staging/'recovery.json').write_text(json.dumps(metadata,indent=2)+'\n')
        spec = load_yall_spec(staging/'Yallfile')
        tasks = {t.name:t for t in spec.tasks}
        if len(tasks) != 93 or len(tasks['summary'].parents) != 13 or any(n.startswith(('convert-','pedestal-','transfer-')) for n in tasks):
            raise ValueError('Recovery graph is not the expected 93-node downstream graph')
        for ped, run, scan in PAIRS:
            if tasks[f'mip-{ped}-{run}-{scan}'].parents != ('build',):
                raise ValueError('Recovery MIP does not depend on new build')
        if destination.exists():
            raise ValueError('Destination appeared during preparation')
        staging.rename(destination)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    print(destination)


def verify_root(metadata_path):
    if os.environ.get('ARI_RF_BATCH_WORKER') != '1':
        raise ValueError('ROOT checks must execute inside the Condor worker')
    import ROOT
    ROOT.gROOT.SetBatch(True)
    for item in read_json(metadata_path)['transfers']:
        path = Path(item['path']); stat = path.stat()
        if (stat.st_size,stat.st_mtime_ns) != (item['size_bytes'],item['mtime_ns']):
            raise ValueError(f'Transfer changed after preparation: {path}')
        f = ROOT.TFile.Open(str(path), 'READ')
        if not f or f.IsZombie() or f.TestBit(ROOT.TFile.kRecovered):
            raise ValueError(f'Unreadable or recovered ROOT file: {path}')
        try:
            counts = {}
            for tree_name, branch in [('Setup','setup'),('Data','event'),('Calib','calib')]:
                tree = f.Get(tree_name)
                if not tree or not tree.InheritsFrom('TTree') or tree.GetEntries() <= 0 or not tree.GetBranch(branch):
                    raise ValueError(f'Missing/nonempty tree or branch {tree_name}/{branch}: {path}')
                counts[tree_name] = int(tree.GetEntries())
            print(json.dumps({'transfer':str(path),'entries':counts}), flush=True)
        finally:
            f.Close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--previous-workspace', type=Path)
    parser.add_argument('--campaign', type=Path)
    parser.add_argument('--eic-shell', type=Path)
    parser.add_argument('--verify-root', type=Path, help=argparse.SUPPRESS)
    a=parser.parse_args()
    try:
        if a.verify_root: verify_root(a.verify_root)
        elif all((a.destination,a.previous_workspace,a.campaign,a.eic_shell)):
            prepare(a.destination,a.previous_workspace,a.campaign,a.eic_shell)
        else: parser.error('Required: --destination --previous-workspace --campaign --eic-shell')
    except (ValueError, OSError, KeyError) as exc: parser.error(str(exc))
