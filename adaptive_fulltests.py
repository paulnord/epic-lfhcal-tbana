#!/usr/bin/env python3
"""Prepare/run isolated BNL old-versus-minimal-adaptive full MIP-chain tests.

prepare runs on the submission host and never submits jobs. Worker subcommands
run inside the existing EIC container through the generated Yallfile wrapper.
All source snapshots, builds and outputs belong to a fresh campaign directory.
"""
import argparse
import csv
import difflib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tarfile
import time

BASE = '924ad82de6d150534b4d7684b5638df92c0a2016'
KIT = '84c841c7b41c01f6e8ea4ca88eacbbed5a6dfce3'
DECODER = '2a7f7d4e8b760ff9f9406e36d31e99c5b6fffa2c'
WRAPPER_REF = 'a6973071179440437a4ab33a054c9e875dc0a15e'
SPECS = {
    'b2': dict(fullset='FullSetB_2', pedestal=126, muons=[127,128,129,130,131,132,133], toa='B'),
    'e1': dict(fullset='FullSetE_1', pedestal=372, muons=[373,374,375,376,377,378], toa='E'),
    # The production E3 recipe deliberately uses the FullSetF ToA offsets.
    'e3': dict(fullset='FullSetE_3', pedestal=471, muons=[473,474,477,478,481,482], toa='F'),
}
MODELS = ('legacy', 'adaptive')
STAGES = ('mip', 'select', 'refine1', 'refine2', 'refine3', 'refine4', 'refine5')


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temp.replace(path)


def load(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write_csv(path, rows):
    if not rows:
        raise ValueError('Refusing to write an empty report: '+str(path))
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: '?' if row.get(k) is None else row[k] for k in fields})


def git(repo, *args):
    return subprocess.check_output(['git','-C',str(repo),*args])


def snapshot(repo, ref, dest):
    """Only committed content; ignore caller's dirty working tree and builds."""
    dest.mkdir(parents=True, exist_ok=True)
    data = git(repo, 'archive', '--format=tar', ref)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            p = Path(member.name)
            if p.is_absolute() or '..' in p.parts:
                raise ValueError('Unsafe archive member: '+member.name)
            if member.issym() or member.islnk():
                target = (dest/p.parent/member.linkname).resolve()
                if os.path.commonpath([str(dest.resolve()), str(target)]) != str(dest.resolve()):
                    raise ValueError('Archive link escapes snapshot: '+member.name)
        archive.extractall(dest)
    return hashlib.sha256(data).hexdigest()


def tree_hashes(root):
    return {str(p.relative_to(root)):digest(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts}


def check_sources(out, model):
    src = out/'sources'/model
    for relative, expected in load(out/'source-hashes.json')[model].items():
        if digest(src/relative) != expected:
            raise ValueError('Source changed during campaign: '+str(src/relative))
    return src


def file_info(path, hashed=False):
    path = Path(path).resolve()
    s = path.stat()
    if not path.is_file() or not os.access(path, os.R_OK) or s.st_size == 0:
        raise ValueError('Input missing, empty or unreadable: '+str(path))
    result = dict(path=str(path), size=s.st_size, mtime_ns=s.st_mtime_ns)
    if hashed:
        result['sha256'] = digest(path)
    return result


def check_info(info):
    actual = file_info(info['path'])
    if any(actual[k] != info[k] for k in ('path','size','mtime_ns')):
        raise ValueError('Input changed after preparation: '+info['path'])


def find_inputs(code, work, archive, data):
    spec = SPECS[code]
    name = spec['fullset']
    roots = [work/f'fullset-{code}-repro', work/f'adaptive-fullset-{code}-repro',
             archive/f'fullset-{code}-repro']
    for root in roots:
        p = root/'transfer'/f'rawHGCROC_wPed_wBC_Muon_{name}.root'
        if p.is_file():
            return dict(mode='transfer', files={'transfer':file_info(p)})
    for root in roots:
        merged = root/'converted'/f'rawHGCROC_Muon_{name}.root'
        ped = root/'pedestal'/'rawHGCROC_wPed.root'
        if merged.is_file() and ped.is_file():
            return dict(mode='converted', files={'merged':file_info(merged),'pedestal':file_info(ped)})
    # No reduced/selected-file fallback: that would not test the first MIP pass.
    raw = {str(r):data/f'Run{r}.h2g' for r in [spec['pedestal']]+spec['muons']}
    missing = [str(p) for p in raw.values() if not p.is_file()]
    if missing:
        raise ValueError(code+': no pre-MIP transfer or converted+pedestal pair; raw fallback missing: '
                         +', '.join(missing))
    return dict(mode='raw', files={r:file_info(p) for r,p in raw.items()})


def stop(proc):
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except ProcessLookupError:
        pass


def run(command, cwd, log, timeout=10800, env=None):
    """Time the subprocess; do not relabel timeouts as completed runs."""
    command = [str(x) for x in command]
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    begin = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    print('RUN', ' '.join(command), '\nLOG',log,flush=True)
    with log.open('w') as stream:
        proc = subprocess.Popen(command,cwd=str(cwd),env=env,stdout=stream,
                                stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
            outcome = 'returned' if code == 0 else 'failed'
        except subprocess.TimeoutExpired:
            stop(proc)
            code, outcome = proc.returncode, 'timeout'
        except BaseException:
            stop(proc)
            raise
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    timing = dict(command=command,cwd=str(cwd),returncode=code,outcome=outcome,
                  wall_s=time.monotonic()-begin,
                  cpu_s=(after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime),
                  log=str(log),timeout_s=timeout)
    dump(str(log)+'.json',timing)
    if outcome != 'returned':
        tail = '\n'.join(log.read_text(errors='replace').splitlines()[-35:])
        raise RuntimeError(f'{outcome}: {log}\n{tail}')
    return timing


def root_open(path):
    import ROOT
    ROOT.gROOT.SetBatch(True)
    f = ROOT.TFile.Open(str(path),'READ')
    if not f or f.IsZombie() or f.TestBit(ROOT.TFile.kRecovered):
        raise ValueError('Invalid/incomplete ROOT file: '+str(path))
    return f


def check_root(path, events=False):
    f = root_open(path)
    try:
        trees = {k.GetName():int(f.Get(k.GetName()).GetEntries())
                 for k in f.GetListOfKeys() if k.GetClassName()=='TTree'}
        if events and max(trees.values(),default=0) <= 1:
            raise ValueError('No nonempty event tree: '+str(path))
        return trees
    finally:
        f.Close()


def build(out, model):
    src = check_sources(out,model)
    directory = src/'NewStructure'/'build'
    logs = out/'build-logs'/model
    if model == 'adaptive':
        run([sys.executable,'-m','unittest','-v','test_apply_adaptive_minimal.py'],src,logs/'patch-tests.log',120)
        exe = src/'test-adaptive-numerics'
        run(['c++','-std=c++17','-O2','NewStructure/tests/test_adaptive_minimal.cc','-o',exe],src,logs/'numerics-build.log',120)
        run([exe],src,logs/'numerics-test.log',180)
        run(['root','-l','-b','-q','NewStructure/tests/test_adaptive_minimal_root.C()'],src,logs/'root-test.log',300)
    run(['cmake','-S',src/'NewStructure','-B',directory,'-DCMAKE_BUILD_TYPE=Release'],src,logs/'configure.log',600)
    targets = ['DataPrep','Convert'] if model=='legacy' else ['DataPrep']
    run(['cmake','--build',directory,'--target',*targets,'-j','4'],src,logs/'build.log',3600)
    artifacts = {str(directory/n):digest(directory/n) for n in ('DataPrep','libLFHCAL.so')}
    version = subprocess.check_output(['root-config','--version'],text=True).strip()
    dump(out/f'build-{model}.json',dict(model=model,artifacts=artifacts,root_version=version))


def environment(out, model):
    ready = load(out/f'build-{model}.json')
    for path, sha in ready['artifacts'].items():
        if digest(path) != sha:
            raise ValueError('Compiled artifact changed: '+path)
    version = subprocess.check_output(['root-config','--version'],text=True).strip()
    if version != ready['root_version']:
        raise ValueError('ROOT version differs from the build')
    directory = out/'sources'/model/'NewStructure'/'build'
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = str(directory)+os.pathsep+env.get('LD_LIBRARY_PATH','')
    env['OMP_NUM_THREADS'] = '1'
    env['ROOT_MAX_THREADS'] = '1'
    # A stale external libLFHCAL must not be loaded instead of this variant.
    linked = subprocess.check_output(['ldd',str(directory/'DataPrep')],env=env,text=True)
    if str(directory/'libLFHCAL.so') not in linked:
        raise ValueError('DataPrep does not resolve the expected libLFHCAL.so:\n'+linked)
    return directory/'DataPrep',env


def common_input(out, code):
    manifest = load(out/'manifest.json')
    spec, incoming = SPECS[code], manifest['inputs'][code]
    work = out/'inputs'/code
    work.mkdir(parents=True,exist_ok=True)
    (work/'plots-pedestal').mkdir(exist_ok=True)
    (work/'plots-transfer').mkdir(exist_ok=True)
    source = check_sources(out,'legacy')
    exe,env = environment(out,'legacy')
    cfg = source/'configs'/'TB2026'
    db = cfg/'DataTakingDB_TBSPSH2_202605_HGCROC.csv'
    for info in incoming['files'].values():
        check_info(info)
    files = {k:Path(v['path']) for k,v in incoming['files'].items()}
    if incoming['mode']=='transfer':
        transfer = files['transfer']
    else:
        if incoming['mode']=='raw':
            converted = {}
            for key,raw in files.items():
                converted[key] = work/f'rawHGCROC_{key}.root'
                run([exe.with_name('Convert'),'-d','0','-f','-w','-c',raw,
                     '-o',converted[key],'-m',cfg/'mapping_HGCROC_SPSH2TB_sumV2_default.csv','-r',db],
                    source/'NewStructure',work/f'convert-{key}.log',env=env)
                check_root(converted[key],events=True)
            files['merged'] = work/f'rawHGCROC_Muon_{spec["fullset"]}.root'
            run(['hadd','-f',files['merged'],*[converted[str(r)] for r in spec['muons']]],
                source/'NewStructure',work/'merge.log',env=env)
            files['pedestal'] = work/'rawHGCROC_wPed.root'
            run([exe,'-a','-d','1','-p','-i',converted[str(spec['pedestal'])],'-f',
                 '-o',files['pedestal'],'-O',work/'plots-pedestal','-r',db,'-F','pdf'],
                source/'NewStructure',work/'pedestal.log',env=env)
        check_root(files['merged'],events=True)
        check_root(files['pedestal'])
        transfer = work/f'rawHGCROC_wPed_wBC_Muon_{spec["fullset"]}.root'
        run([exe,'-d','1','-e','-f','-P',files['pedestal'],'-i',files['merged'],
             '-o',transfer,'-O',work/'plots-transfer','-r',db,
             '-B',cfg/'badChannel_HGCROC_SPSTB2026_FullSetA-F.txt',
             '-G',cfg/f'ToAOffsets_TBSPS2026_FullSet{spec["toa"]}.csv'],
            source/'NewStructure',work/'transfer.log',env=env)
    trees = check_root(transfer,events=True)
    # Hash once on a worker rather than making submission wait for large reads.
    dump(work/'ready.json',dict(transfer=file_info(transfer,hashed=True),trees=trees,
                              boundary='before initial MIP calibration',mode=incoming['mode']))


def paths(out, model, code, stage):
    name = SPECS[code]['fullset']
    if stage=='mip':
        stem = f'rawHGCROC_wPedwMuon_wBC_Muon_{name}'
    elif stage=='select':
        stem = f'rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_{name}'
    else:
        n = int(stage.replace('refine',''))
        token = 'ImpR' if n==1 else f'Imp{n}R'
        stem = f'rawHGCROC_wPedwMuon_wBC_{token}_Muon_{name}'
    directory = out/model/code/stage
    return dict(directory=directory, root=directory/(stem+'.root'),
                calib=directory/(stem+'_calib.txt'), hists=directory/(stem+'_Hists.root'),
                report=directory/'cells.csv', summary=directory/'stage.json')


def stage_command(out,model,code,stage,exe):
    p = paths(out,model,code,stage)
    db = out/'sources'/model/'configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv'
    if stage=='mip':
        incoming = load(out/'inputs'/code/'ready.json')['transfer']
        check_info(incoming)
        args = ['-a','-f','-d','1','-e','-s','-i',incoming['path']]
    elif stage=='select':
        args = ['-f','-d','1','-X','-i',paths(out,model,code,'mip')['root']]
    else:
        args = ['-x','-a','-f','-d','1','-S','-i',paths(out,model,code,'select')['root']]
        n = int(stage.replace('refine',''))
        if n>1:
            args += ['-k',paths(out,model,code,f'refine{n-1}')['calib']]
    args += ['-o',p['root']]
    if stage!='select':
        args += ['-O',p['directory']/'plots','-r',db]
    return [exe,*args]


def calibrations(path):
    rows = {}
    for line in Path(path).read_text().splitlines():
        f = line.split()
        if len(f)!=18 or not f[0].isdigit():
            continue
        cell = int(f[0])
        if cell in rows:
            raise ValueError('Duplicate calibration cell')
        scale,width = float(f[9]),float(f[10])
        if not math.isfinite(scale) or not math.isfinite(width):
            raise ValueError('Nonfinite saved calibration')
        rows[cell] = dict(cell_id=cell,bc=int(f[17]),
                          scale_h=None if scale==-1000 else scale,
                          fwhm_h=None if width==-1000 else width)
    if not rows:
        raise ValueError('No calibration rows: '+str(path))
    return rows


def audit_stage(out,model,code,stage):
    p = paths(out,model,code,stage)
    trees = check_root(p['root'],events=stage in ('mip','select'))
    if stage=='select':
        dump(p['summary'],dict(model=model,dataset=code,stage=stage,event_trees=trees))
        return
    cals = calibrations(p['calib'])
    f = root_open(p['hists'])
    rows=[]
    try:
        d = f.Get('IndividualCellsTrigg')
        if not d:
            raise ValueError('Missing triggered histogram directory: '+str(p['hists']))
        for cell,cal in sorted(cals.items()):
            h = d.Get(f'hspectramipTriggADCCellID{cell}')
            fit = d.Get(f'fmipmipTriggHGCellID{cell}')
            row = dict(model=model,dataset=code,stage=stage,**cal,
                       histogram_present=bool(h),fit_saved=bool(fit))
            if h:
                counts = [float(h.GetBinContent(i)) for i in range(h.GetNbinsX()+2)]
                if not all(math.isfinite(v) and v>=0 for v in counts):
                    raise ValueError('Invalid histogram contents')
                fingerprint = dict(counts=counts,nbins=h.GetNbinsX(),
                                   xmin=h.GetXaxis().GetXmin(),xmax=h.GetXaxis().GetXmax())
                row.update(entries=float(h.GetEntries()),integral=float(h.Integral(1,h.GetNbinsX())),
                           histogram_sha256=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest())
            if fit:
                pars = [float(fit.GetParameter(i)) for i in range(4)]
                if not all(math.isfinite(v) for v in pars):
                    raise ValueError('Nonfinite stored fit parameters')
                for i,key in enumerate(('landau_width','mpv','area','gaussian_sigma')):
                    row[key]=pars[i]
                    err=float(fit.GetParError(i))
                    row[key+'_err']=err if math.isfinite(err) else None
                chi=float(fit.GetChisquare()); ndf=int(fit.GetNDF())
                row.update(chi2=chi if math.isfinite(chi) else None,ndf=ndf,
                           chi2_ndf=chi/ndf if ndf>0 and math.isfinite(chi) else None,
                           fit_xmin=float(fit.GetXmin()),fit_xmax=float(fit.GetXmax()))
            rows.append(row)
    finally:
        f.Close()
    write_csv(p['report'],rows)
    valid = [r['scale_h'] for r in rows if r['scale_h'] is not None and r['bc']>=2]
    dump(p['summary'],dict(model=model,dataset=code,stage=stage,cell_rows=len(rows),
         saved_fits=sum(r['fit_saved'] for r in rows),
         available_calibrations=len(valid),mean_scale_h=sum(valid)/len(valid) if valid else None,
         total_trigger_entries=sum(r.get('entries',0) for r in rows),event_trees=trees,
         note='An available calibration may be carried forward; fit_saved is separate.'))


def stage_run(out, model, code, stage):
    source = check_sources(out,model)
    exe,env=environment(out,model)
    p=paths(out,model,code,stage)
    if p['directory'].exists() and any(p['directory'].iterdir()):
        raise ValueError('Preserving earlier stage output: '+str(p['directory']))
    p['directory'].mkdir(parents=True,exist_ok=True)
    (p['directory']/'plots').mkdir(exist_ok=True)
    timing=run(stage_command(out,model,code,stage,exe),source/'NewStructure',p['directory']/'DataPrep.log',env=env)
    # Separate process verifies actual on-disk output without a live callback.
    run([sys.executable,Path(__file__),'audit','--out',out,'--model',model,'--dataset',code,'--stage',stage],
        source/'NewStructure',p['directory']/'audit.log',600,env)
    report=load(p['summary']);report['execution']=timing
    dump(p['summary'],report)
    print('COMPLETED',model,code,stage,flush=True)


def maybe_float(value):
    return None if value in (None,'?','') else float(value)


def compare(out, code):
    combined=[]; summaries=[]
    for stage in STAGES:
        reports={m:load(paths(out,m,code,stage)['summary']) for m in MODELS}
        summaries.append(dict(stage=stage,**reports))
        if stage=='select':
            continue
        tables={}
        for model in MODELS:
            with paths(out,model,code,stage)['report'].open() as f:
                tables[model]={int(r['cell_id']):r for r in csv.DictReader(f)}
        if tables['legacy'].keys()!=tables['adaptive'].keys():
            raise ValueError('Mismatched calibration cell keys')
        for cell in sorted(tables['legacy']):
            a,b=tables['legacy'][cell],tables['adaptive'][cell]
            row=dict(dataset=code,stage=stage,cell_id=cell,
                     legacy_fit_saved=a['fit_saved'],adaptive_fit_saved=b['fit_saved'],
                     same_histogram=(a.get('histogram_sha256') not in (None,'','?') and a.get('histogram_sha256')==b.get('histogram_sha256')))
            for key in ('scale_h','fwhm_h','entries','mpv','landau_width','gaussian_sigma','chi2_ndf'):
                x,y=maybe_float(a.get(key)),maybe_float(b.get(key))
                row['legacy_'+key]=x;row['adaptive_'+key]=y
                row['delta_'+key]=None if x is None or y is None else y-x
                if key in ('scale_h','fwhm_h'):
                    row['rel_delta_'+key]=None if x in (None,0) or y is None else (y-x)/x
            combined.append(row)
    directory=out/'reports';directory.mkdir(exist_ok=True)
    write_csv(directory/f'{code}-comparison.csv',combined)
    dump(directory/f'{code}-stages.json',summaries)


def summary(out):
    rows=[];reports={}
    for code in SPECS:
        with (out/'reports'/f'{code}-comparison.csv').open() as f:
            rows.extend(csv.DictReader(f))
        reports[code]=load(out/'reports'/f'{code}-stages.json')
    write_csv(out/'all-cell-stage-comparisons.csv',rows)
    dump(out/'summary.json',dict(scope='3 datasets, two full MIP chains each, 6 fit passes per chain',
         datasets=reports,numerical_review_only=True,
         note='No automatic scientific acceptance; review selection and calibration trajectories.'))


def yallfile(out):
    lines=['campaign lfhcal-minimal-adaptive-fullchains','backend condor','',
           '%cpus 1','%memory 8GB','%disk 16GB','%time 4h','%getenv true',
           f'%wrapper {out}/run-in-eic-shell.sh {load(out/"manifest.json")["eic_shell"]} /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1','']
    def task(name,deps,cmd,outputs,extra=()):
        lines.append(name+':'+(' '+' '.join(deps) if deps else ''))
        lines.extend('    '+x for x in extra)
        lines.append('    @input runner '+str(out/'adaptive_fulltests.py'))
        lines.append('    @input manifest '+str(out/'manifest.json'))
        lines.append('    @input sources '+str(out/'source-hashes.json'))
        for i,p in enumerate(outputs):lines.append(f'    @output out{i} {p}')
        lines.append('    python3 @input.runner '+cmd+' --out '+str(out))
        lines.append('')
    for m in MODELS:
        task('build-'+m,[],f'build --model {m}',[out/f'build-{m}.json'],['%cpus 4','%time 2h'])
    for c in SPECS:
        task('input-'+c,['build-legacy','build-adaptive'],f'input --dataset {c}',
             [out/'inputs'/c/'ready.json'],['%time 24h'])
        for m in MODELS:
            previous='input-'+c
            for stage in STAGES:
                p=paths(out,m,c,stage)
                products=[p['root'],p['summary']]
                if stage!='select':products += [p['calib'],p['hists'],p['report']]
                name=f'{stage}-{m}-{c}'
                task(name,[previous],f'stage --model {m} --dataset {c} --stage {stage}',products)
                previous=name
        task('compare-'+c,[f'refine5-{m}-{c}' for m in MODELS],f'compare --dataset {c}',
             [out/'reports'/f'{c}-comparison.csv',out/'reports'/f'{c}-stages.json'])
    task('summary',['compare-'+c for c in SPECS],'summary',[out/'summary.json',out/'all-cell-stage-comparisons.csv'])
    return '\n'.join(lines)+'\n'


def prepare(args):
    out=args.out.resolve();repo=args.repo.resolve()
    for p in (out,repo,args.work.resolve(),args.eic_shell.resolve()):
        if any(c.isspace() or c in '{}\"\'' for c in str(p)):
            raise ValueError('This launcher requires paths without whitespace/braces/quotes')
    if out.exists():
        raise ValueError('Use a NEW campaign directory; refusing '+str(out))
    if not args.eic_shell.is_file() or not os.access(args.eic_shell,os.X_OK):
        raise ValueError('EIC shell missing or not executable')
    for ref in (BASE,KIT,WRAPPER_REF):git(repo,'cat-file','-e',ref+'^{commit}')
    inputs={c:find_inputs(c,args.work.resolve(),args.archive.resolve(),args.data.resolve()) for c in SPECS}
    for c,v in inputs.items():
        print(c,':',v['mode'],*(r['path'] for r in v['files'].values()),sep='\n  ',flush=True)
    out.mkdir(parents=True)
    shutil.copy2(Path(__file__),out/'adaptive_fulltests.py')
    decoder_repo=repo/'NewStructure/h2g_decode'
    try:
        if not (decoder_repo/'.git').exists():raise ValueError('No initialized decoder')
        git(decoder_repo,'cat-file','-e',DECODER+'^{commit}')
    except (subprocess.CalledProcessError,ValueError):
        decoder_repo=out/'decoder-cache'
        subprocess.run(['git','clone','--no-checkout','https://github.com/tlprotzman/h2g_decode.git',str(decoder_repo)],check=True)
        git(decoder_repo,'cat-file','-e',DECODER+'^{commit}')
    archives={}
    for model,ref in (('legacy',BASE),('adaptive',KIT)):
        dest=out/'sources'/model
        archives[model]=snapshot(repo,ref,dest)
        snapshot(decoder_repo,DECODER,dest/'NewStructure/h2g_decode')
    adaptive=out/'sources/adaptive'
    old=(adaptive/'NewStructure/TileSpectra.cc').read_text()
    subprocess.run([sys.executable,str(adaptive/'apply_adaptive_minimal.py'),'--repo',str(adaptive),'--apply'],check=True,
                   stdout=(out/'core-patch-application.log').open('w'))
    new=(adaptive/'NewStructure/TileSpectra.cc').read_text()
    (out/'core.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
                                     fromfile='a/NewStructure/TileSpectra.cc',tofile='b/NewStructure/TileSpectra.cc')))
    wrapper=git(repo,'show',WRAPPER_REF+':tools/run-in-eic-shell.sh')
    (out/'run-in-eic-shell.sh').write_bytes(wrapper);(out/'run-in-eic-shell.sh').chmod(0o755)
    hashes={m:tree_hashes(out/'sources'/m) for m in MODELS}
    # No unnoticed core or configuration change is allowed in the comparison.
    different=[p for p,h in hashes['legacy'].items() if hashes['adaptive'].get(p)!=h]
    if different != ['NewStructure/TileSpectra.cc']:
        raise ValueError('Unexpected base-to-candidate differences: '+repr(different))
    dump(out/'source-hashes.json',hashes)
    dump(out/'manifest.json',dict(base_commit=BASE,kit_commit=KIT,decoder_commit=DECODER,
         source_archive_sha256=archives,core_patch_sha256=digest(out/'core.patch'),
         eic_shell=str(args.eic_shell.resolve()),eic_shell_sha256=digest(args.eic_shell),
         wrapper_commit=WRAPPER_REF,inputs=inputs,specs=SPECS,
         source_boundary='git archives plus exact fingerprint-checked minimal core patch',
         does_not_use_dirty_worktree=True,created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    (out/'Yallfile').write_text(yallfile(out))
    print('\nPREPARED:',out,'\n51 tasks: 2 builds + 3 shared inputs + 42 chain stages + 3 comparisons + summary.\nNo jobs submitted.',flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=('prepare','build','input','stage','audit','compare','summary'))
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--repo',type=Path)
    ap.add_argument('--work',type=Path,default=Path('/gpfs01/star/scratch/pnord/lfhcal'))
    ap.add_argument('--archive',type=Path,default=Path('/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBanalysis'))
    ap.add_argument('--data',type=Path,default=Path('/gpfs01/star/pwg/pnord/eic/2026TBdata'))
    ap.add_argument('--eic-shell',type=Path)
    ap.add_argument('--model',choices=MODELS)
    ap.add_argument('--dataset',choices=tuple(SPECS))
    ap.add_argument('--stage',choices=STAGES)
    a=ap.parse_args();a.out=a.out.resolve()
    needs={'prepare':('repo','eic_shell'),'build':('model',),'input':('dataset',),
           'stage':('model','dataset','stage'),'audit':('model','dataset','stage'),
           'compare':('dataset',),'summary':()}
    for key in needs[a.action]:
        if getattr(a,key) is None:ap.error('Missing --'+key.replace('_','-'))
    try:
        if a.action=='prepare':prepare(a)
        elif a.action=='build':build(a.out,a.model)
        elif a.action=='input':common_input(a.out,a.dataset)
        elif a.action=='stage':stage_run(a.out,a.model,a.dataset,a.stage)
        elif a.action=='audit':audit_stage(a.out,a.model,a.dataset,a.stage)
        elif a.action=='compare':compare(a.out,a.dataset)
        else:summary(a.out)
    except Exception as exc:
        print('FAILED:',exc,file=sys.stderr,flush=True)
        raise SystemExit(1)


if __name__=='__main__':main()
