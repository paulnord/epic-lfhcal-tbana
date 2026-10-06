#!/usr/bin/env python3
"""Write native, table-driven PS/SPS Yallfiles; never execute or submit jobs.

Python is used only at setup time. Convert, pedestal extraction, transfer,
MIP calibration, selection and each refinement are explicit Yallfile commands.
"""
import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

SOURCE_REF = 'd689941726f35e4eba8fc7586b9de4f3d31a3bb7'
DECODER_REF = '2a7f7d4e8b760ff9f9406e36d31e99c5b6fffa2c'
BUNDLE_PATH = 'examples/yall/calibration-2026'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def safe_path(path):
    value = os.path.abspath(os.path.expanduser(str(path)))
    if not re.fullmatch(r'[A-Za-z0-9_./+\-]+', value):
        raise ValueError('Yallfile paths must not contain spaces or shell syntax: '+value)
    return Path(value)


def snapshot(repo, ref, destination):
    data = git(repo, 'archive', '--format=tar', ref)
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            p = Path(member.name)
            if p.is_absolute() or '..' in p.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Unsupported source archive member: '+member.name)
        archive.extractall(destination)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def apply_overrides(recipes, overrides):
    allowed = {'pedestal', 'toa', 'mapping', 'muon_runs'}
    for name, changes in overrides.items():
        if name not in recipes or not isinstance(changes, dict):
            raise ValueError('Unknown set or invalid override: '+name)
        if set(changes)-allowed:
            raise ValueError('Unknown override keys for '+name)
        r = recipes[name]
        if r['campaign'] != 'ps':
            raise ValueError('SPS scan pair changes must be made in the catalog, not a PS override')
        if 'pedestal' in changes:
            p = changes['pedestal']
            if type(p) is not int or p < 1:
                raise ValueError('pedestal must be a positive run number')
            r['pedestal_runs'] = [p]
            r['pedestal_evidence'] = 'explicit setup override'
            r['review_needed'] = [x for x in r['review_needed'] if x != 'pedestal association inferred']
        for field in ('toa', 'mapping'):
            if field in changes:
                value = changes[field]
                if not isinstance(value, str) or not value or not re.fullmatch(r'[A-Za-z0-9_.+/-]+', value):
                    raise ValueError(field+' must be a config filename or absolute path')
                if field == 'mapping' and value == 'none':
                    raise ValueError('mapping cannot be none')
                r[field] = value
                if field == 'toa':
                    r['review_needed'] = [x for x in r['review_needed'] if not x.startswith('ToA choice')]
        if 'muon_runs' in changes:
            runs = changes['muon_runs']
            if not isinstance(runs, list) or not runs or any(type(x) is not int or x < 1 for x in runs) or len(set(runs)) != len(runs):
                raise ValueError('muon_runs must be a nonempty list of distinct positive integers')
            r['muon_runs'] = runs
        if set(r['muon_runs']) & set(r['pedestal_runs']):
            raise ValueError('A run cannot be both pedestal and muon in '+name)
        r['setup_overrides'] = changes


def config(value):
    return value if value.startswith('/') else '{CFG}/'+value


def render(name, recipe, root, raw, source, shell, fitter='legacy', boundary='original', refinements=5):
    r = recipe
    ps = r['campaign'] == 'ps'
    work = root/name
    rows = [('pedestal', p) for p in r['pedestal_runs']]+[('muon', p) for p in r['muon_runs']]
    rows += [('unpaired', p) for p in r.get('extra_raw_runs', [])]
    pairs = [(r['pedestal_runs'][0], r['sample'])] if ps else [(p['pedestal'], '%03d' % p['muon']) for p in r['pedestal_muon_pairs']]
    lines = [f'# {name}: {fitter} fitter, {boundary} boundary; {refinements} refinements.',
             '# Native tasks: no Python calibration runner and no automatic submission.',
             '# Pedestal evidence: '+r['pedestal_evidence']]
    lines += ['# NOTE: '+x for x in r.get('notes', [])]
    lines += ['# DRAFT: '+x for x in r['review_needed']]
    lines += [f'campaign lfhcal-2026-{name}-{fitter}-{boundary}', 'backend condor',
              '%account-provenance off', '%cpus 1', '%memory 8GB', '%disk 16GB',
              '%time 10h', '%getenv true',
              f'@set WORK {work}', f'@set SOURCE {source}', f'@set BUILD {work}/build',
              f'@set CFG {source}/configs/TB2026',
              f'@set RAW {raw}/{"ps-2026" if ps else "sps-2026"}/raw',
              f'%wrapper {root}/run-in-eic-shell.sh {shell} {root}/in-calibration-build.sh {{BUILD}}', '',
              '# File role and run number drive conversion. Leading zeros are filenames.',
              '@table runs type run:']
    lines += ['    %-9s %03d' % row for row in rows]
    lines += ['', '# Each sample has exactly one pedestal. Scan samples remain separate.', '@table pairs ped sample:']
    lines += ['    %03d %s' % p for p in pairs]
    lines += ['']

    def task(label, parents, inputs, outputs, command, each=None, extra=()):
        lines.append(label+':'+(' '+parents if parents else ''))
        if each:
            lines.append('    @each '+each)
        lines.extend('    '+x for x in extra)
        lines.extend('    @input '+k+' '+v for k, v in inputs)
        lines.extend('    @output '+k+' '+v for k, v in outputs)
        lines.append('    '+command)
        lines.append('')

    task('build', '', [('cmake', '{SOURCE}/NewStructure/CMakeLists.txt'),
                      ('decoder', '{SOURCE}/NewStructure/h2g_decode/CMakeLists.txt')],
         [('convert', '{BUILD}/Convert'), ('dataprep', '{BUILD}/DataPrep'), ('library', '{BUILD}/libLFHCAL.so')],
         '! cmake -S {SOURCE}/NewStructure -B {BUILD} -DCMAKE_BUILD_TYPE=Release && '
         'cmake --build {BUILD} --target Convert DataPrep -j 4', extra=('%cpus 4', '%time 2h'))
    stages = ['converted', 'pedestal', 'transfer', 'mip', 'select', 'final']+['refine'+str(i) for i in range(1, refinements+1)]
    task('prepare', 'build', [], [], '/bin/mkdir -p '+' '.join('{WORK}/'+s for s in stages)+
         ' '+' '.join('{WORK}/plots/'+s for s in stages if s not in ('converted', 'select', 'final')))
    db = ('rundb', config(r['rundb']))
    task('convert-{type}-{run}', 'prepare', [('raw', '{RAW}/Run{run}.h2g'), ('mapping', config(r['mapping'])), db],
         [('root', '{WORK}/converted/rawHGCROC_{run}.root')],
         '{BUILD}/Convert -d 0 -f -w -c @input.raw -o @output.root -m @input.mapping -r @input.rundb',
         'type run in runs', ('%memory 4GB', '%time 24h'))
    task('pedestal-{ped}', 'convert-pedestal-{ped}', [('raw', '{WORK}/converted/rawHGCROC_{ped}.root'), db],
         [('root', '{WORK}/pedestal/rawHGCROC_wPed_{ped}.root'),
          ('calib', '{WORK}/pedestal/rawHGCROC_wPed_{ped}_calib.txt'),
          ('hists', '{WORK}/pedestal/rawHGCROC_wPed_{ped}_Hists.root'),
          ('plots', '{WORK}/plots/pedestal/Run{ped}')],
         '{BUILD}/DataPrep -a -d 1 -p -i @input.raw -f -o @output.root -O @output.plots -r @input.rundb -F png',
         'ped in pairs.ped')
    if ps:
        task('merge-{type}', 'convert-{type}-{run}', [('parts', '{WORK}/converted/rawHGCROC_{run}.root')],
             [('root', '{WORK}/converted/rawHGCROC_'+r['sample']+'.root')],
             'hadd -f @output.root @input.parts', 'type muon')
    lines += ['# -P transfers pedestal constants; -B loads the bad-channel map; -G loads ToA offsets.']
    transfer_inputs = [('pedestal', '{WORK}/pedestal/rawHGCROC_wPed_{ped}.root'),
                       ('raw', '{WORK}/converted/rawHGCROC_{sample}.root'), ('bad', config(r['badmap'])), db]
    toa_flag = ''
    if r['toa'] != 'none':
        transfer_inputs.append(('toa', config(r['toa'] or 'UNASSIGNED_TOA_'+name+'.csv')))
        toa_flag = ' -G @input.toa'
    else:
        lines.append('# Explicit override: no ToA offsets (-G omitted).')
    task('transfer-{ped}-{sample}', ('merge-muon' if ps else 'convert-muon-{sample}')+' pedestal-{ped}', transfer_inputs,
         [('root', '{WORK}/transfer/rawHGCROC_wPed_wBC_{sample}.root'), ('plots', '{WORK}/plots/transfer/{sample}')],
         '{BUILD}/DataPrep -d 1 -e -f -P @input.pedestal -i @input.raw -o @output.root -O @output.plots '
         '-r @input.rundb -B @input.bad'+toa_flag+' -F png', 'ped sample in pairs')
    def products(stage, stem):
        base = '{WORK}/'+stage+'/'+stem
        return [('root', base+'.root'), ('calib', base+'_calib.txt'), ('hists', base+'_Hists.root'),
                ('plots', '{WORK}/plots/'+stage+'/{sample}')]
    mip_stem = 'rawHGCROC_wPedwMuon_wBC_{sample}'
    selected = '{WORK}/select/rawHGCROC_mipTrigg_wPedwMuon_wBC_{sample}.root'
    task('mip-{ped}-{sample}', 'transfer-{ped}-{sample}', [('root', '{WORK}/transfer/rawHGCROC_wPed_wBC_{sample}.root'), db],
         products('mip', mip_stem),
         '{BUILD}/DataPrep -a -f -d 1 -e -s -i @input.root -o @output.root -O @output.plots -r @input.rundb -F png')
    task('select-{ped}-{sample}', 'mip-{ped}-{sample}', [('root', '{WORK}/mip/'+mip_stem+'.root')], [('root', selected)],
         '{BUILD}/DataPrep -f -d 1 -X -i @input.root -o @output.root')
    lines += ['# Every refinement reads the same selected event file.',
              '# -S refits the MIP; -x avoids another event-tree copy; -k carries the preceding constants.']
    previous = 'select-{ped}-{sample}'
    last_products = None
    for n in range(1, refinements+1):
        stage = 'refine'+str(n)
        inputs = [('root', selected), db]
        carry = ''
        if last_products:
            inputs.append(('calib', dict(last_products)['calib']))
            carry = ' -k @input.calib'
        last_products = products(stage, 'rawHGCROC_wPedwMuon_wBC_'+('ImpR' if n == 1 else 'Imp%dR' % n)+'_{sample}')
        task(stage+'-{ped}-{sample}', previous, inputs, last_products,
             '{BUILD}/DataPrep -x -a -f -d 1 -S -i @input.root'+carry+
             ' -o @output.root -O @output.plots -r @input.rundb -F png')
        previous = stage+'-{ped}-{sample}'
    final_inputs = [(k, v) for k, v in last_products if k in ('root', 'calib')]
    task('final-{ped}-{sample}', previous, final_inputs,
         [('root', '{WORK}/final/calib_Final_{sample}.root'), ('calib', '{WORK}/final/calib_Final_{sample}_calib.txt')],
         '! /bin/cp @input.root @output.root && /bin/cp @input.calib @output.calib')
    return '\n'.join(lines)+'\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--ref', default='FETCH_HEAD', help='Commit supplying this setup bundle')
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--eic-shell', type=Path, required=True)
    parser.add_argument('--sets', nargs='+', help='Default: all 17 PS sets and three SPS scan groups')
    parser.add_argument('--fitter', choices=['legacy', 'adaptive'], default='legacy')
    parser.add_argument('--boundary', choices=['original', 'valley'], default='original')
    parser.add_argument('--refinements', type=int, default=5, help='Default: five, matching the earlier F1 campaign')
    parser.add_argument('--overrides', type=Path, help='JSON keyed by PS set: pedestal, toa, mapping, muon_runs')
    args = parser.parse_args(argv)
    if not 1 <= args.refinements <= 8:
        parser.error('--refinements must be 1..8')
    repo, root, raw, shell = map(safe_path, (args.repo, args.out, args.raw, args.eic_shell))
    if root.exists():
        raise ValueError('Use a new output directory; preserving '+str(root))
    if not shell.is_file() or not os.access(shell, os.X_OK):
        raise ValueError('EIC shell is missing or not executable: '+str(shell))
    bundle_ref = git(repo, 'rev-parse', args.ref+'^{commit}').decode().strip()
    bundle = {name: git(repo, 'show', bundle_ref+':'+BUNDLE_PATH+'/'+name)
              for name in ('calibration_2026_sets.json', 'run-in-eic-shell.sh', 'in-calibration-build.sh')}
    catalog = json.loads(bundle['calibration_2026_sets.json'])
    recipes = copy.deepcopy(catalog['sets'])
    if args.overrides:
        apply_overrides(recipes, json.loads(args.overrides.read_text()))
    selected = args.sets or list(recipes)
    if len(selected) != len(set(selected)) or any(s not in recipes for s in selected):
        raise ValueError('Unknown or duplicate set in --sets')
    git(repo, 'cat-file', '-e', SOURCE_REF+'^{commit}')
    decoder = repo/'NewStructure/h2g_decode'
    try:
        if Path(git(decoder, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != decoder.resolve():
            raise ValueError('Decoder submodule is not initialized')
        git(decoder, 'cat-file', '-e', DECODER_REF+'^{commit}')
    except (OSError, ValueError, subprocess.CalledProcessError):
        raise ValueError('Initialize the existing decoder first: git -C "'+str(repo)+'" submodule update --init NewStructure/h2g_decode')
    root.mkdir(parents=True)
    source = root/'source'
    snapshot(repo, SOURCE_REF, source)
    decoder_dir = source/'NewStructure/h2g_decode'
    if decoder_dir.exists():
        decoder_dir.rmdir()
    snapshot(decoder, DECODER_REF, decoder_dir)
    if args.fitter == 'adaptive':
        with (root/'adaptive-patch.log').open('w') as log:
            subprocess.run([sys.executable, str(source/'apply_adaptive_minimal.py'), '--repo', str(source), '--apply'], check=True, stdout=log)
    if args.boundary == 'valley':
        patcher = module(source/'apply_mip_range.py', 'range_patch')
        patcher.apply(source, source/'NewStructure/MipRangeFinder.h')
    for name in ('run-in-eic-shell.sh', 'in-calibration-build.sh'):
        (root/name).write_bytes(bundle[name])
        (root/name).chmod(0o755)
    manifest = dict(source_commit=SOURCE_REF, decoder_commit=DECODER_REF, bundle_commit=bundle_ref,
                    recipe_commit=catalog['recipe_commit'], fitter=args.fitter, boundary=args.boundary,
                    refinements=args.refinements, raw=str(raw), eic_shell=str(shell), sets={})
    table = []
    ready, draft = [], []
    for name in selected:
        r = recipes[name]
        for field in ('mapping', 'rundb', 'badmap', 'toa'):
            value = r[field]
            if value and value != 'none':
                path = Path(value) if value.startswith('/') else source/'configs/TB2026'/value
                if not path.is_file():
                    raise ValueError('Configuration file missing: '+str(path))
        directory = root/name
        (directory/'build').mkdir(parents=True)
        filename = 'Yallfile.draft' if r['review_needed'] else 'Yallfile'
        (directory/filename).write_text(render(name, r, root, raw, source, shell, args.fitter, args.boundary, args.refinements))
        (directory/'recipe.json').write_text(json.dumps(r, indent=2)+'\n')
        (draft if r['review_needed'] else ready).append(name)
        manifest['sets'][name] = dict(yallfile=str(directory/filename), recipe=r)
        roles = [('pedestal', r['pedestal_runs']), ('muon', r['muon_runs']), ('unpaired', r.get('extra_raw_runs', []))]
        for role, runs in roles:
            for run in runs:
                file = raw/('ps-2026' if r['campaign'] == 'ps' else 'sps-2026')/'raw'/('Run%03d.h2g' % run)
                table.append(dict(set=name, type=role, run=run, path=str(file),
                                  local_nonempty=file.is_file() and file.stat().st_size > 0))
        print(name+': '+filename+(' | '+', '.join(r['review_needed']) if r['review_needed'] else ''), flush=True)
    hashes = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(source.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    (root/'source-hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
    (root/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    with (root/'run-files.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    (root/'ready-sets.txt').write_text(''.join(n+'\n' for n in ready))
    (root/'draft-sets.txt').write_text(''.join(n+'\n' for n in draft))
    print('Prepared %d complete recipes and %d drafts at %s' % (len(ready), len(draft), root))
    print('Raw files are only checked locally for presence; downloads may still be running.')
    print('No ROOT processing or jobs submitted. Review Yallfile, then yall-run validate and yall-run plan.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('ERROR: '+str(error), file=sys.stderr)
        sys.exit(1)
