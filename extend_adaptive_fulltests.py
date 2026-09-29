#!/usr/bin/env python3
"""Prepare a separate full-chain campaign for FullSets not in an earlier one.

Uses the pinned, already-tested launcher and the archived FullSet Yallfiles.
No source, build, job, or result in the earlier campaign is changed. The newly
prepared campaign builds its own isolated legacy/adaptive binaries on Condor.
This command prepares only; it never submits jobs.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import pprint
import re
import subprocess
import sys
import tempfile

BASE = '924ad82de6d150534b4d7684b5638df92c0a2016'
KIT = '84c841c7b41c01f6e8ea4ca88eacbbed5a6dfce3'
RUNNER_REF = '43cefa06c47cdda1e4ebdcc1b8d84c33df587953'
RUNNER_BLOB = '1fc0a8a3f81fd558769f17a34ba2426bf2b9b122'
RECIPES_REF = 'd91f36a04ce68d4b16e755a292e537d59fb855bc'
ALL_SETS = ('b1','b2','c1','c2','c3','d1','d2','e1','e2','e3','f1','f2','g1','g2')
CONFIG_PREFIX = 'configs/TB2026/'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def blob_sha(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def parse_recipe(code, text):
    """Read only explicit run-table/config facts; no inferred family settings."""
    active = '\n'.join(line.split('#',1)[0].rstrip() for line in text.splitlines())
    lines = active.splitlines()
    starts = [i for i,line in enumerate(lines) if line.strip() == '@table runs type run:']
    if len(starts) != 1:
        raise ValueError(f'{code}: expected one @table runs type run')
    pairs = []
    for line in lines[starts[0]+1:]:
        if not line.strip():
            continue
        if not line[0].isspace():
            break
        words = line.split()
        if len(words)!=2 or words[0] not in ('pedestal','muon') or not words[1].isdigit():
            raise ValueError(f'{code}: unexpected run-table row {line!r}')
        pairs.append((words[0],int(words[1])))
    if len(pairs)!=len(set(pairs)):
        raise ValueError(f'{code}: duplicate run-table rows')
    peds = [run for kind,run in pairs if kind=='pedestal']
    muons = [run for kind,run in pairs if kind=='muon']
    if len(peds)!=1 or not muons or peds[0] in muons:
        raise ValueError(f'{code}: need one pedestal and distinct muon runs')
    def one(pattern):
        values = sorted(set(re.findall(pattern,active)))
        if len(values)!=1:
            raise ValueError(f'{code}: expected one explicit config, found {values}')
        return values[0]
    fullset = f'FullSet{code[0].upper()}_{code[1:]}'
    if fullset not in active:
        raise ValueError(f'{code}: recipe does not name {fullset}')
    mapping = one(r'mapping_HGCROC_SPSH2TB_sumV[0-9]+_default\.csv')
    bad = one(r'badChannel_HGCROC_SPSTB2026_FullSet[A-Za-z0-9_-]+\.txt')
    toa_file = one(r'ToAOffsets_TBSPS2026_FullSet[A-Za-z0-9_]+\.csv')
    return dict(fullset=fullset,pedestal=peds[0],muons=muons,
                toa=toa_file[len('ToAOffsets_TBSPS2026_FullSet'):-len('.csv')],
                mapping=mapping,bad_channels=bad,toa_file=toa_file)


def remaining_sets(previous, requested=None):
    if previous.get('base_commit')!=BASE or previous.get('kit_commit')!=KIT:
        raise ValueError('Earlier campaign uses different fitter versions; refusing to mix studies')
    old = previous.get('specs')
    if not isinstance(old,dict) or not old or set(old)-set(ALL_SETS):
        raise ValueError('Earlier manifest has an invalid FullSet catalog')
    chosen = tuple(requested) if requested else tuple(c for c in ALL_SETS if c not in old)
    if not chosen or len(chosen)!=len(set(chosen)) or set(chosen)-set(ALL_SETS):
        raise ValueError('Choose a nonempty, unique list of known FullSets')
    overlap = set(chosen)&set(old)
    if overlap:
        raise ValueError('Already covered by earlier campaign: '+', '.join(sorted(overlap)))
    return chosen


def once(source, old, new):
    if source.count(old)!=1:
        raise ValueError('Pinned launcher anchor missing or ambiguous: '+repr(old))
    return source.replace(old,new,1)


def expand_launcher(source, specs, provenance):
    """Only catalog/config routing/report labels change; fitter code is untouched."""
    tree = ast.parse(source)
    assignments = [node for node in tree.body if isinstance(node,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=='SPECS' for t in node.targets)]
    if len(assignments)!=1:
        raise ValueError('Expected one launcher SPECS assignment')
    node = assignments[0]
    lines = source.splitlines(keepends=True)
    source = ''.join(lines[:node.lineno-1])+('SPECS = '+pprint.pformat(specs)+'\n'
              +'EXTENSION = '+pprint.pformat(provenance)+'\n')+''.join(lines[node.end_lineno:])
    source = once(source,"cfg/'mapping_HGCROC_SPSH2TB_sumV2_default.csv'","cfg/spec['mapping']")
    source = once(source,"cfg/'badChannel_HGCROC_SPSTB2026_FullSetA-F.txt'","cfg/spec['bad_channels']")
    source = once(source,"cfg/f'ToAOffsets_TBSPS2026_FullSet{spec[\"toa\"]}.csv'","cfg/spec['toa_file']")
    # Newer F/G recipes name pedestal products with their run number.
    source = once(source, "        ped = root/'pedestal'/'rawHGCROC_wPed.root'",
                  "        ped = root/'pedestal'/'rawHGCROC_wPed.root'\n"
                  "        if not ped.is_file():\n"
                  "            ped = root/'pedestal'/f\"rawHGCROC_wPed_{spec['pedestal']}.root\"")
    source = once(source,"dict(base_commit=BASE,kit_commit=KIT,decoder_commit=DECODER,",
                  "dict(extension=EXTENSION,base_commit=BASE,kit_commit=KIT,decoder_commit=DECODER,")
    source = once(source,"scope='3 datasets, two full MIP chains each, 6 fit passes per chain'",
                  "scope=f'{len(SPECS)} datasets, two full MIP chains each, 6 fit passes per chain'")
    old_message = '51 tasks: 2 builds + 3 shared inputs + 42 chain stages + 3 comparisons + summary.'
    n = len(specs)
    message = f'{3+16*n} tasks: 2 builds + {n} shared inputs + {14*n} chain stages + {n} comparisons + summary.'
    source = once(source,old_message,message)
    source = once(source,"campaign lfhcal-minimal-adaptive-fullchains",
                  "campaign lfhcal-minimal-adaptive-fullchains-extension")
    compile(source,'adaptive_fulltests.py','exec')
    return source


def safe_new_destination(out,previous,repo):
    if out.exists():
        raise ValueError('Use a NEW output directory; preserving '+str(out))
    for root in (previous,repo):
        if out == root or root in out.parents or out in root.parents:
            raise ValueError('New outputs must be separate from the earlier campaign and checkout')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--previous',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--work',type=Path,default=Path('/gpfs01/star/scratch/pnord/lfhcal'))
    ap.add_argument('--archive',type=Path,default=Path('/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBanalysis'))
    ap.add_argument('--data',type=Path,default=Path('/gpfs01/star/pwg/pnord/eic/2026TBdata'))
    ap.add_argument('--eic-shell',type=Path,required=True)
    ap.add_argument('--datasets',nargs='+',choices=ALL_SETS,
                    help='Default: all FullSets absent from --previous; overlap is rejected')
    args = ap.parse_args()
    repo,previous,out = args.repo.resolve(),args.previous.resolve(),args.out.resolve()
    try:
        safe_new_destination(out,previous,repo)
        previous_bytes = (previous/'manifest.json').read_bytes()
        old = json.loads(previous_bytes)
        selected = remaining_sets(old,args.datasets)
        raw = git(repo,'show',RUNNER_REF+':adaptive_fulltests.py')
        if blob_sha(raw)!=RUNNER_BLOB:
            raise ValueError('Unexpected original launcher fingerprint')
        specs,recipe_hashes = {},{}
        # Read the pinned run recipes, including their explicit configuration
        # paths. This retains the G mapping/bad-map and C3/E3 ToA exceptions.
        for code in ALL_SETS:
            path = f'examples/yall/fullset-{code}-repro/Yallfile'
            recipe = git(repo,'show',RECIPES_REF+':'+path)
            spec = parse_recipe(code,recipe.decode('utf-8'))
            if code in old['specs']:
                for key in ('fullset','pedestal','muons','toa'):
                    if spec[key]!=old['specs'][code][key]:
                        raise ValueError(f'Earlier {code} recipe differs at {key}; review before expanding')
            if code not in selected:
                continue
            # All named configurations must exist at the same production base.
            for key in ('mapping','bad_channels','toa_file'):
                git(repo,'cat-file','-e',BASE+':'+CONFIG_PREFIX+spec[key])
            specs[code] = spec
            recipe_hashes[code] = dict(path=path,sha256=hashlib.sha256(recipe).hexdigest())
        provenance = dict(previous_campaign_root=str(previous),
            previous_manifest_sha256=hashlib.sha256(previous_bytes).hexdigest(),
            excluded_previous_datasets=list(old['specs']),datasets=list(specs),
            runner_ref=RUNNER_REF,runner_blob=RUNNER_BLOB,recipes_ref=RECIPES_REF,
            recipes=recipe_hashes,extension_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            policy='New snapshots/builds/outputs only; no writes into the earlier campaign')
        generated = expand_launcher(raw.decode('utf-8'),specs,provenance)
        print('Earlier campaign retained: '+', '.join(old['specs']),flush=True)
        print('Additional datasets: '+', '.join(specs),flush=True)
        print(f'{2*len(specs)} full calibration chains; {12*len(specs)} fit passes; '
              f'{3+16*len(specs)} Condor tasks.',flush=True)
        with tempfile.TemporaryDirectory(prefix='lfhcal-extension-') as tmp:
            runner = Path(tmp)/'adaptive_fulltests.py'
            runner.write_text(generated)
            subprocess.run([sys.executable,str(runner),'prepare','--repo',str(repo),
                '--work',str(args.work.resolve()),'--archive',str(args.archive.resolve()),
                '--data',str(args.data.resolve()),'--eic-shell',str(args.eic_shell.resolve()),
                '--out',str(out)],check=True)
        print('\nPrepared only. Run yall-run validate/plan/create/start in:',out,flush=True)
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        print('FAILED:',error,file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':
    main()
