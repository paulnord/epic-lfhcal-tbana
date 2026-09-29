#!/usr/bin/env python3
"""Prepare a NEW D1-only campaign after the two confirmed 3-hour timeouts.

Reuses the pinned campaign generator, not the failed output ROOT files.
No edits/deletes/submissions in the old campaign. The new campaign rebuilds
identical sources, rechecks the exact pre-MIP input and runs both full chains.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

EXTENSION_REF = '33d5c499635da4ddcdf9332b0f9e4d69a4adc4b3'
EXTENSION_BLOB = '6e6aec96f997056f84670090bba81682c156a31f'
CHILD_SECONDS = 8 * 3600
SCHEDULER_HOURS = 10


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def inspect_previous(previous, base, kit):
    old = read(previous/'manifest.json')
    if old.get('base_commit') != base or old.get('kit_commit') != kit:
        raise ValueError('Different fitter versions; refusing mixed studies')
    if 'd1' not in old.get('specs', {}):
        raise ValueError('The previous campaign must contain D1')
    evidence = {}
    for model in ('legacy', 'adaptive'):
        directory = previous/model/'d1'/'mip'
        if (directory/'stage.json').exists():
            raise ValueError('D1 already has a stage report; inspect instead of retrying')
        path = directory/'DataPrep.log.json'
        timing = read(path)
        if timing.get('outcome') != 'timeout' or timing.get('timeout_s') != 10800:
            raise ValueError('Expected the confirmed 10800-second D1 timeout: ' + str(path))
        evidence[model] = dict(path=str(path), sha256=sha(path), timing=timing)
    ready_path = previous/'inputs'/'d1'/'ready.json'
    ready = read(ready_path)
    if ready.get('boundary') != 'before initial MIP calibration':
        raise ValueError('Input is not explicitly marked as pre-MIP')
    info = ready['transfer']
    path = Path(info['path']).resolve(strict=True)
    if previous/'legacy' in path.parents or previous/'adaptive' in path.parents:
        raise ValueError('A fit output cannot be used as the pre-MIP input')
    stat = path.stat()
    if not path.is_file() or stat.st_size != info['size'] or stat.st_mtime_ns != info['mtime_ns']:
        raise ValueError('Original pre-MIP input metadata changed')
    checksum = info.get('sha256', '')
    if len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum):
        raise ValueError('Missing original pre-MIP input SHA-256')
    return old, info, evidence


def change_budgets(source, extension):
    source = extension.once(source, 'timeout=10800, env=None',
                            'timeout=28800, env=None')
    source = extension.once(source, "'%time 4h'", "'%time 10h'")
    source = extension.once(source, 'campaign lfhcal-minimal-adaptive-fullchains-extension',
                            'campaign lfhcal-minimal-adaptive-d1-timeout-recovery')
    # Freeze the same pre-MIP input, not whichever archive a new search finds.
    source = extension.once(source,
        'inputs={c:find_inputs(c,args.work.resolve(),args.archive.resolve(),args.data.resolve()) for c in SPECS}',
        "inputs={'d1': dict(mode='transfer', files={'transfer': EXTENSION['transfer']})}")
    source = extension.once(source,
        "    dump(work/'ready.json',dict(transfer=file_info(transfer,hashed=True),trees=trees,",
        "    checked = file_info(transfer,hashed=True)\n"
        "    if checked['sha256'] != EXTENSION['transfer']['sha256']:\n"
        "        raise ValueError('Pre-MIP input content changed since the failed campaign')\n"
        "    dump(work/'ready.json',dict(transfer=checked,trees=trees,")
    compile(source, 'adaptive_fulltests.py', 'exec')
    return source


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--previous', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--eic-shell', type=Path, required=True)
    args = ap.parse_args()
    repo, previous, out = args.repo.resolve(), args.previous.resolve(), args.out.resolve()
    raw_extension = git(repo, 'show', EXTENSION_REF+':extend_adaptive_fulltests.py')
    if blob(raw_extension) != EXTENSION_BLOB:
        raise ValueError('Unexpected extension-generator fingerprint')
    with tempfile.TemporaryDirectory(prefix='lfhcal-d1-recovery-') as tmp:
        extension_path = Path(tmp)/'extension.py'
        extension_path.write_bytes(raw_extension)
        spec = importlib.util.spec_from_file_location('pinned_extension', str(extension_path))
        ext = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ext)
        ext.safe_new_destination(out, previous, repo)
        old, transfer, evidence = inspect_previous(previous, ext.BASE, ext.KIT)
        recipe_path = 'examples/yall/fullset-d1-repro/Yallfile'
        recipe_bytes = git(repo, 'show', ext.RECIPES_REF+':'+recipe_path)
        recipe = ext.parse_recipe('d1', recipe_bytes.decode())
        if recipe != old['specs']['d1']:
            raise ValueError('D1 recipe differs from the failed campaign')
        runner_bytes = git(repo, 'show', ext.RUNNER_REF+':adaptive_fulltests.py')
        if blob(runner_bytes) != ext.RUNNER_BLOB:
            raise ValueError('Unexpected original runner fingerprint')
        provenance = dict(previous_campaign_root=str(previous),
            previous_manifest_sha256=sha(previous/'manifest.json'), timeout_evidence=evidence,
            datasets=['d1'], transfer=transfer, child_timeout_s=CHILD_SECONDS,
            scheduler_stage_limit_s=SCHEDULER_HOURS*3600,
            extension_ref=EXTENSION_REF, runner_ref=ext.RUNNER_REF,
            recipes_ref=ext.RECIPES_REF, recipe_sha256=hashlib.sha256(recipe_bytes).hexdigest(),
            recovery_script_sha256=sha(Path(__file__)),
            policy='New snapshots/builds/outputs only; old outputs untouched; no fit/model changes')
        expanded = ext.expand_launcher(runner_bytes.decode(), {'d1': recipe}, provenance)
        generated = change_budgets(expanded, ext)
        runner = Path(tmp)/'adaptive_fulltests.py'
        runner.write_text(generated)
        subprocess.run([sys.executable, str(runner), 'prepare', '--repo', str(repo),
                        '--eic-shell', str(args.eic_shell.resolve()), '--out', str(out)], check=True)
        (out/'recovery-launcher.patch').write_text(''.join(difflib.unified_diff(
            expanded.splitlines(True), generated.splitlines(True),
            fromfile='before-timeout-repair.py', tofile='after-timeout-repair.py')))
        # No changes to core code/configuration relative to the failed campaign.
        if read(out/'source-hashes.json') != read(previous/'source-hashes.json'):
            raise ValueError('Source snapshots differ from the previous campaign; DO NOT SUBMIT')
        (out/'RECOVERY_READY.json').write_text(json.dumps(dict(
            previous=str(previous), source_hashes_identical=True, tasks=19,
            child_timeout_s=CHILD_SECONDS, scheduler_stage_limit_s=SCHEDULER_HOURS*3600,
            launcher_sha256=sha(out/'adaptive_fulltests.py'), yallfile_sha256=sha(out/'Yallfile'),
            note='D1-only results; earlier campaign summary remains blocked'), indent=2)+'\n')
    print('\nRECOVERY READY: 19 tasks, D1 only, identical fitter sources.', flush=True)
    print('8-hour analysis timeout; 10-hour scheduler limit; no jobs submitted.', flush=True)
    print('Old partial files and 13 completed datasets remain untouched.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print('FAILED:', exc, file=sys.stderr)
        raise SystemExit(1)
