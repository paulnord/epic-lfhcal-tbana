#!/usr/bin/env python3
"""Prepare (do not submit) a B2 R6-R8 continuation from the supplied R5 runner."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parent", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    parent, out = args.parent.resolve(), args.out.resolve()
    for p in (parent, out):
        if any(c.isspace() or c in "{}\"'" for c in str(p)):
            raise ValueError("Paths must not contain whitespace, braces, or quotes")
    if out.exists():
        raise ValueError("Use a new output directory: " + str(out))
    original = parent / "adaptive_fulltests.py"
    source = original.read_text()
    ns = runpy.run_path(str(original))
    old_stages = ('mip', 'select', 'refine1', 'refine2', 'refine3', 'refine4', 'refine5')
    if ns['STAGES'] != old_stages:
        raise ValueError("Unexpected parent stage list")
    manifest = json.loads((parent / 'manifest.json').read_text())
    shell = Path(manifest['eic_shell'])
    if sha(shell) != manifest['eic_shell_sha256']:
        raise ValueError("EIC shell differs from the original campaign")
    required = [parent/'source-hashes.json', parent/'run-in-eic-shell.sh']
    for model in ns['MODELS']:
        required.append(parent/f'build-{model}.json')
        for stage in old_stages:
            p = ns['paths'](parent, model, 'b2', stage)
            required.append(p['summary'])
            if stage != 'select':
                required.append(p['report'])
        required += [ns['paths'](parent, model, 'b2', 'select')['root'],
                     ns['paths'](parent, model, 'b2', 'refine5')['calib']]
        r5 = json.loads(ns['paths'](parent, model, 'b2', 'refine5')['summary'].read_text())
        if r5.get('execution', {}).get('returncode') != 0:
            raise ValueError(model + ' R5 has no successful execution record')
    for p in required:
        if not p.is_file() or p.stat().st_size == 0:
            raise ValueError("Missing or empty prerequisite: " + str(p))

    replacements = [
        ("STAGES = " + repr(old_stages),
         "STAGES = " + repr(old_stages + ('refine6', 'refine7', 'refine8'))),
        ('    directory = out/model/code/stage',
         '    directory = (Path(' + repr(str(out)) + ')/model/code/stage '
         'if stage in ("refine6", "refine7", "refine8") else out/model/code/stage)'),
        ("    directory=out/'reports';directory.mkdir(exist_ok=True)",
         "    directory=Path(" + repr(str(out)) + ")/'reports';directory.mkdir(exist_ok=True)"),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError("Runner differs from reviewed source at: " + before)
        source = source.replace(before, after, 1)
    compile(source, 'adaptive_fulltests_r8.py', 'exec')
    out.mkdir(parents=True)
    runner = out/'adaptive_fulltests_r8.py'
    runner.write_text(source)
    shutil.copy2(original, out/'adaptive_fulltests_original.py')
    shutil.copy2(parent/'run-in-eic-shell.sh', out/'run-in-eic-shell.sh')
    ext = runpy.run_path(str(runner))
    lines = ['campaign lfhcal-b2-r6-r8', 'backend condor', '',
             '%cpus 1', '%memory 8GB', '%disk 16GB', '%time 4h', '%getenv true',
             f'%wrapper {out}/run-in-eic-shell.sh {shell} /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1', '']

    def task(name, deps, command, products, inputs):
        lines.append(name + ':' + (' ' + ' '.join(deps) if deps else ''))
        common = [('runner', runner), ('manifest', parent/'manifest.json'),
                  ('sources', parent/'source-hashes.json')]
        for key, path in common + inputs:
            lines.append(f'    @input {key} {path}')
        for i, path in enumerate(products):
            lines.append(f'    @output out{i} {path}')
        lines.append(f'    python3 @input.runner {command} --out {parent}')
        lines.append('')

    for model in ns['MODELS']:
        for n in range(6, 9):
            stage = f'refine{n}'
            p = ext['paths'](parent, model, 'b2', stage)
            prev = ext['paths'](parent, model, 'b2', f'refine{n-1}')
            deps = [] if n == 6 else [f'refine{n-1}-{model}-b2']
            task(f'{stage}-{model}-b2', deps,
                 f'stage --model {model} --dataset b2 --stage {stage}',
                 [p[k] for k in ('root', 'summary', 'calib', 'hists', 'report')],
                 [('previous_calibration', prev['calib']),
                  ('selected_events', ns['paths'](parent, model, 'b2', 'select')['root']),
                  ('build_record', parent/f'build-{model}.json')])
    task('compare-b2-r8', [f'refine8-{m}-b2' for m in ns['MODELS']],
         'compare --dataset b2',
         [out/'reports/b2-comparison.csv', out/'reports/b2-stages.json'], [])
    (out/'Yallfile').write_text('\n'.join(lines) + '\n')
    record = dict(parent=str(parent), output=str(out), dataset='b2',
                  models=list(ns['MODELS']), new_stages=['refine6','refine7','refine8'],
                  original_runner_sha256=sha(original), runner_sha256=sha(runner),
                  parent_manifest_sha256=sha(parent/'manifest.json'),
                  source_hashes_sha256=sha(parent/'source-hashes.json'),
                  wrapper_sha256=sha(out/'run-in-eic-shell.sh'),
                  changes=['allow R6-R8', 'route new stage outputs to extension',
                           'route comparison reports to extension'],
                  prerequisite_files=[dict(path=str(p), size=p.stat().st_size,
                      mtime_ns=p.stat().st_mtime_ns) for p in required])
    (out/'extension.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Prepared:', out)
    print('7 tasks: 3 sequential refinements per method, followed by comparison.')
    print('Original binaries, ROOT version, and source checks remain enforced.')
    print('New outputs and reports:', out)
    print('No jobs submitted. Run yall-run validate and yall-run plan here.')


if __name__ == '__main__':
    main()
