#!/usr/bin/env python3
"""Prepare waveform-only parameter scans from proven completed calibrations.

Host preparation reads bounded campaign metadata and file stats only. ROOT,
compilation, tests and waveform event processing are worker-only. Never submits.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

SCRIPT = Path(os.path.abspath(__file__))
REPO = SCRIPT.parents[3]
RF_RUNS = (298, 300, 304, 306, 310, 329, 333, 335, 337, 339, 341, 343, 345)
OTHER_RUNS = (347, 349, 351, 353, 355, 357, 359, 361, 363)
GROUPS = (RF_RUNS, OTHER_RUNS, (302,))
RUNS = tuple(sorted(RF_RUNS + OTHER_RUNS + (302,)))
MAX_JSON = 16 * 1024 * 1024


def safe(path):
    path = Path(path)
    if not path.is_absolute() or re.search(r'[^A-Za-z0-9_/.-]', str(path)):
        raise ValueError(f'Use absolute paths containing only letters, digits, /_.-: {path}')
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    if path.stat().st_size > MAX_JSON:
        raise ValueError(f'Metadata exceeds {MAX_JSON} bytes: {path}')
    return json.loads(path.read_text())


def record(path):
    safe(path)
    st = path.stat()
    if not path.is_file() or not os.access(path, os.R_OK) or st.st_size <= 0:
        raise ValueError(f'Missing, empty or unreadable input: {path}')
    return {'path': str(path), 'realpath': str(path.resolve()),
            'size_bytes': st.st_size, 'mtime_ns': st.st_mtime_ns}


def unchanged(item):
    now = record(Path(item['path']))
    changed = [k for k in ('realpath', 'size_bytes', 'mtime_ns') if now[k] != item[k]]
    if changed:
        details = '; '.join(f'{k}: recorded={item[k]!r}, current={now[k]!r}' for k in changed)
        raise ValueError(f'Input changed since preparation: {item["path"]}; {details}')


def unique_campaigns(campaigns):
    """Deduplicate real directories, but retain the first supplied shared path."""
    selected = {}
    for campaign in campaigns:
        logical = Path(os.path.abspath(campaign))
        selected.setdefault(logical.resolve(), logical)
    return sorted(selected.values())


def discover(roots, max_depth=5, max_directories=10000):
    """Look only for small campaign metadata, never enumerate data/source trees."""
    found = []
    count = 0
    def walk_error(error):
        raise error
    for root in roots:
        safe(root)
        if not root.is_dir():
            raise ValueError(f'Search root does not exist: {root}')
        for here, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
            count += 1
            if count > max_directories:
                raise ValueError('Discovery directory limit reached; supply --campaign paths')
            depth = len(Path(here).relative_to(root).parts)
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and
                             d not in {'source', 'build', 'products', 'raw', 'results', 'logs', 'state'}
                             and '_attempt_' not in d and not (Path(here)/d).is_symlink())
            if depth >= max_depth:
                dirs[:] = []
            if 'campaign.json' in files:
                found.append(Path(os.path.abspath(here)))
                dirs[:] = []
    return unique_campaigns(found)


def completed(campaign, name, task):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
        raise ValueError('Unsafe task name in metadata')
    sp = campaign/'state'/f'{name}.json'
    state = read_json(sp)
    n = state.get('attempts')
    if state.get('state') != 'completed' or state.get('last_returncode') != 0 or type(n) is not int or n < 1:
        raise ValueError(f'{name}: latest state is not completed successfully')
    ap = campaign/f'{name}_attempt_{n:03d}'/'attempt.json'
    attempt = read_json(ap)
    if (attempt.get('task'), attempt.get('attempt'), attempt.get('state'),
        attempt.get('returncode'), attempt.get('command_returncode')) != (name, n, 'completed', 0, 0):
        raise ValueError(f'{name}: latest attempt did not complete successfully')
    if attempt.get('command') != task.get('command'):
        raise ValueError(f'{name}: attempt command differs from frozen task')
    return attempt, {str(sp): sha(sp), str(ap): sha(ap)}


def campaign_inputs(campaign):
    manifest_path = campaign/'campaign.json'
    manifest = read_json(manifest_path)
    tasks = manifest.get('tasks', {})
    if manifest.get('backend') != 'condor' or not isinstance(tasks, dict):
        raise ValueError('Not a supported Condor campaign')
    archive = campaign/'Yallfile'
    if manifest.get('spec_archive', {}).get('sha256') != sha(archive):
        raise ValueError('Archived recipe hash mismatch')
    if (campaign/'amendments').exists() and any((campaign/'amendments').iterdir()):
        raise ValueError('Amended campaign requires manual provenance review')
    results, errors, duplicate_runs = {}, [], set()
    for name, task in tasks.items():
        if not name.startswith('calibrate-'):
            continue
        for output in task.get('outputs', []):
            path = Path(output.get('path', ''))
            match = re.fullmatch(r'calibratedHGCROC_Run_(\d+)\.root', path.name)
            if output.get('role') != 'root' or not match or int(match[1]) not in RUNS:
                continue
            run = int(match[1])
            if run in results or run in duplicate_runs:
                results.pop(run, None)
                duplicate_runs.add(run)
                errors.append(f'run{run}: {campaign}: Multiple calibrated outputs for one run')
                continue
            try:
                item = record(path)
                attempt, proofs = completed(campaign, name, task)
                records = [x for x in attempt.get('outputs', []) if x.get('role') == 'root']
                if len(records) != 1 or Path(records[0]['path']).resolve() != path.resolve():
                    raise ValueError('Recorded calibration output path mismatch')
                old = records[0]
                if not old.get('exists') or any(old.get(k) != item[k] for k in ('size_bytes', 'mtime_ns')):
                    raise ValueError('Calibration changed since successful attempt')
                # Recover the actual waveform options, not a guessed input path.
                waves = [t for n, t in tasks.items() if n.startswith('waveform-') and
                         any(x.get('role') == 'root' and Path(x['path']).resolve() == path.resolve()
                             for x in t.get('inputs', []))]
                if len(waves) != 1:
                    raise ValueError('Need exactly one archived waveform consumer')
                command = waves[0]['command']
                args = shlex.split(command) if isinstance(command, str) else list(command)
                expected = ['-d', '1', '-E', '1', '-w', '-i', str(path)]
                if Path(args[0]).name != 'HGCROCStudy' or args[1:8] != expected:
                    raise ValueError('Archived waveform command is not the reviewed native command')
                if len(args) != 16 or args[8] != '-o' or args[10] != '-O' or args[12] != '-r' or args[14] != '-l':
                    raise ValueError('Archived waveform options need manual review')
                configs = {}
                for label, oldpath, filename in [('rundb', args[13], 'DataTakingDB_TBSPSH2_202605_HGCROC.csv'),
                                               ('cells', args[15], 'activeCellsHGCROCParameterScan.txt')]:
                    source = safe(Path(oldpath))
                    target = REPO/'configs/TB2026'/filename
                    if sha(source) != sha(target):
                        raise ValueError(f'Archived {label} differs from current configuration')
                    configs[label] = str(target)
                if run in results:
                    raise ValueError('Multiple calibrated outputs for one run')
                item.update(run=run, campaign=str(campaign), producer=name, command=command,
                            proofs={str(manifest_path): sha(manifest_path), str(archive): sha(archive), **proofs},
                            **configs)
                results[run] = item
            except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
                errors.append(f'run{run}: {campaign}: {exc}')
    return results, errors


def select_inputs(campaigns, runs=RUNS):
    candidates, diagnostics = [], []
    for campaign in unique_campaigns(campaigns):
        try:
            items, errors = campaign_inputs(campaign)
            diagnostics.extend(errors)
            if items:
                candidates.append((campaign, items))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            diagnostics.append(f'{campaign}: {exc}')
    selected = {}
    problems = []
    for run in runs:
        matches = [x[run] for _, x in candidates if run in x]
        if len(matches) == 1:
            selected[run] = matches[0]
        else:
            problems.append(f'run{run}: '+('missing verified calibrated event input' if not matches else
                              'ambiguous calibrated inputs: '+', '.join(x['path'] for x in matches)))
    if problems:
        # Old failed campaigns commonly lack outputs. Do not present their
        # irrelevant errors as lost data when every requested run is verified.
        details = diagnostics if any('missing verified' in p for p in problems) else []
        raise ValueError('\n'.join(problems + ['Supply explicit --campaign paths to narrow discovery. No runs were skipped.'] + details))
    return [selected[r] for r in runs]


def choose_campaigns(campaigns, runs=RUNS):
    """Ask the operator only when history contains competing completed inputs."""
    try:
        select_inputs(campaigns, runs)
        return campaigns
    except ValueError as exc:
        if 'missing verified' in str(exc):
            raise
        print(f'All {len(runs)} requested runs have verified calibrated inputs; source campaigns overlap.')
        print(str(exc))
    eligible = []
    for campaign in unique_campaigns(campaigns):
        try:
            items, _ = campaign_inputs(campaign)
            if items:
                eligible.append(campaign)
                print(f'{len(eligible)}. {campaign} | runs: '+','.join(map(str, sorted(items))))
        except (ValueError, OSError, KeyError, TypeError):
            continue
    # A tty is not seekable: Python's buffered r+ stream fails before reading.
    # Separate one-way streams also work when stdout is piped through tee.
    with open('/dev/tty', 'r') as tty_in, open('/dev/tty', 'w') as tty_out:
        tty_out.write('Choose the completed source campaigns to reuse (comma-separated numbers), or Enter to stop: ')
        tty_out.flush()
        answer = tty_in.readline().strip()
    if not re.fullmatch(r'[1-9][0-9]*(,[1-9][0-9]*)*', answer):
        raise ValueError('No valid campaign selection; nothing prepared or submitted')
    indices = list(map(int, answer.split(',')))
    if len(indices) != len(set(indices)) or any(i > len(eligible) for i in indices):
        raise ValueError('Invalid campaign selection; nothing prepared or submitted')
    chosen = [eligible[i-1] for i in indices]
    select_inputs(chosen, runs)  # Exactly one proven calibration per requested run.
    return chosen


def prepare(destination, campaigns, eic, runs=RUNS):
    for p in (destination, REPO, eic, *campaigns):
        safe(p)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination exists; use a fresh workspace')
    if '.root' in str(destination):
        raise ValueError('Destination must not contain .root (native histogram naming replaces it)')
    if not eic.is_file() or not os.access(eic, os.X_OK):
        raise ValueError('EIC launcher is not executable')
    inputs = select_inputs(campaigns, runs)
    protected = [REPO, *campaigns, *(Path(x['path']).parent.parent.parent for x in inputs)]
    for p in protected:
        if destination.resolve() == p.resolve() or p.resolve() in destination.resolve().parents:
            raise ValueError(f'Destination must be outside source/input workspace/campaign: {p}')
    script = SCRIPT
    wrapper = script.with_name('worker.sh')
    build = script.with_name('build.sh')
    tracked = [script, wrapper, build, REPO/'NewStructure/WaveformAnnotations.h',
               REPO/'configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv',
               REPO/'configs/TB2026/activeCellsHGCROCParameterScan.txt']
    metadata = {'repo': str(REPO), 'commit': subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
                'git_diff': subprocess.check_output(['git', '-C', str(REPO), 'diff', 'HEAD'], text=True),
                'inputs': inputs, 'destination': str(destination), 'eic_shell': str(eic),
                'code_sha256': {str(p): sha(p) for p in tracked},
                'note': f'{len(runs)} requested parameter-scan runs; reuse calibrated event inputs read-only. No calibration, raw conversion, fits or cuts are added. ROOT checks and waveform processing are worker-only.'}
    source = f'''campaign ari-waveform-annotations
backend condor
%account-provenance off
%cpus 1
%memory 4GB
%disk 8GB
%time 2h
%getenv true
%wrapper {wrapper} {eic} /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1

build:
    %retry 0
    %cpus 2
    @input driver {script}
    @input builder {build}
    @input manifest {destination}/preparation.json
    @output ready {destination}/build/ANNOTATIONS_READY
    python3 @input.driver --worker-build @input.manifest
'''
    for item in inputs:
        run = item['run']
        source += f'''
waveform-{run}: build
    %retry 0
    @input driver {script}
    @input manifest {destination}/preparation.json
    @input calibrated {item['path']}
    @input rundb {item['rundb']}
    @input cells {item['cells']}
    @output hists {destination}/products/waveform/calibratedHGCROC_wave_Run_{run}_Hists.root
    @output plots {destination}/products/plots/waveform/Run{run}
    python3 @input.driver --worker-run {run} --manifest @input.manifest
'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.annotations-', dir=destination.parent))
    try:
        (stage/'Yallfile').write_text(source)
        (stage/'preparation.json').write_text(json.dumps(metadata, indent=2)+'\n')
        try:
            from yall_run.model import load_spec
        except ImportError:
            # A pipx/venv yall-run need not be importable by system python3.
            subprocess.run(['yall-run', 'validate', str(stage/'Yallfile')], check=True)
        else:
            spec = load_spec(stage/'Yallfile')
            if len(spec.tasks) != len(inputs) + 1 or any(t.parents != ('build',) for t in spec.tasks if t.name != 'build'):
                raise ValueError('Expected exactly one build plus the requested waveform nodes')
        if destination.exists() or destination.is_symlink():
            raise ValueError('Destination appeared during preparation')
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    for item in inputs:
        print(f"run{item['run']}: {item['path']} (completed {item['producer']})")
    print(f'Prepared {len(inputs)+1} tasks at {destination}; no jobs submitted.')


def worker_metadata(path):
    if os.environ.get('ARI_RF_BATCH_WORKER') != '1':
        raise ValueError('Must execute inside the established Condor worker')
    data = read_json(path)
    repo = data['repo']
    if subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'], text=True).strip() != data['commit'] or subprocess.check_output(['git', '-C', repo, 'diff', 'HEAD'], text=True) != data['git_diff']:
        raise ValueError('Source checkout changed after preparation')
    for p, expected in data['code_sha256'].items():
        if sha(Path(p)) != expected:
            raise ValueError(f'Source/config changed after preparation: {p}')
    for item in data['inputs']:
        unchanged(item)
        for p, expected in item['proofs'].items():
            if sha(Path(p)) != expected:
                raise ValueError(f'Producer provenance changed: {p}')
    return data


def verify_root(item):
    import ROOT
    ROOT.gROOT.SetBatch(True)
    f = ROOT.TFile.Open(item['path'], 'READ')
    if not f or f.IsZombie() or f.TestBit(ROOT.TFile.kRecovered):
        raise ValueError(f'Unreadable or recovered ROOT input: {item["path"]}')
    try:
        for name, branch in [('Setup', 'setup'), ('Data', 'event'), ('Calib', 'calib')]:
            tree = f.Get(name)
            if not tree or not tree.InheritsFrom('TTree') or tree.GetEntries() <= 0 or not tree.GetBranch(branch):
                raise ValueError(f'Missing/nonempty tree or branch {name}/{branch}: {item["path"]}')
    finally:
        f.Close()


def worker_build(path):
    data = worker_metadata(path)
    repo, dest = Path(data['repo']), Path(data['destination'])
    build = dest/'build'
    if build.exists():
        raise ValueError('Build output exists; prepare a fresh campaign rather than retrying')
    subprocess.run(['/bin/bash', str(repo/'examples/yall/ari-rf-batch/build.sh'), str(repo), str(build), str(build/'READY')], check=True)
    for item in data['inputs']:
        verify_root(item)
    (build/'ANNOTATIONS_READY').write_text(f'Build/tests and all {len(data["inputs"])} structural input checks passed.\n')


def worker_run(path, run):
    data = worker_metadata(path)
    dest = Path(data['destination'])
    item = next(x for x in data['inputs'] if x['run'] == run)
    if not (dest/'build/ANNOTATIONS_READY').is_file():
        raise ValueError('Verified build prerequisite is missing')
    verify_root(item)
    output = dest/f'products/waveform/calibratedHGCROC_wave_Run_{run}.root'
    hists = output.with_name(output.stem+'_Hists.root')
    plots = dest/f'products/plots/waveform/Run{run}'
    if any(p.exists() or p.is_symlink() for p in (output, hists, plots)):
        raise ValueError('Output exists; never overwrite or blindly retry waveform analysis')
    output.parent.mkdir(parents=True, exist_ok=True)
    plots.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(dest/'build/HGCROCStudy'), '-d', '1', '-E', '1', '-w', '-i', item['path'],
                    '-o', str(output), '-O', str(plots), '-r', item['rundb'], '-l', item['cells']], check=True)
    unchanged(item)
    record(hists)
    # Native export warnings do not fail HGCROCStudy; explicitly require products.
    report_dirs = None
    for suffix in ('Original.pdf', 'Annotated.pdf', 'Measurements.csv'):
        files = list(plots.rglob(f'WaveformGrid_Run{run}_{suffix}'))
        if not files:
            raise ValueError(f'Missing annotation report for run{run}: {suffix}')
        parents = {f.parent for f in files}
        if report_dirs is not None and parents != report_dirs:
            raise ValueError(f'Incomplete paired reports for run{run}')
        report_dirs = parents
        for f in files:
            record(f)
    print(f'run{run}: histogram and all three annotation products exist; inspect PDFs/CSV before scientific use.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination', type=Path)
    p.add_argument('--runs', nargs='+', type=int, choices=RUNS, default=list(RUNS),
                   help='Only these scan runs (default: all 23); for example --runs 302')
    p.add_argument('--search-root', action='append', type=Path, default=[])
    p.add_argument('--campaign', action='append', type=Path, default=[])
    p.add_argument('--eic-shell', type=Path)
    p.add_argument('--interactive', action='store_true', help='Ask which completed campaigns to reuse if discovery is ambiguous')
    p.add_argument('--worker-build', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--worker-run', type=int, choices=RUNS, help=argparse.SUPPRESS)
    p.add_argument('--manifest', type=Path, help=argparse.SUPPRESS)
    a = p.parse_args()
    try:
        if a.worker_build:
            worker_build(a.worker_build)
        elif a.worker_run is not None and a.manifest:
            worker_run(a.manifest, a.worker_run)
        elif a.destination and a.eic_shell and (a.search_root or a.campaign):
            runs = tuple(sorted(set(a.runs)))
            campaigns = a.campaign + discover(a.search_root)
            if a.interactive:
                campaigns = choose_campaigns(campaigns, runs)
            prepare(a.destination, campaigns, a.eic_shell, runs)
        else:
            p.error('Required: --destination --eic-shell and --search-root or --campaign')
    except (ValueError, OSError, KeyError, StopIteration, subprocess.CalledProcessError) as exc:
        p.error(str(exc))

if __name__ == '__main__':
    main()

