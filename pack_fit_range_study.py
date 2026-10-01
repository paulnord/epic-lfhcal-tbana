#!/usr/bin/env python3
"""Extract frozen LFHCal histograms plus fit/calibration/source context for upload.
Read-only on campaigns; no fitting, selection, rebinning or normalization.
Creates a new directory and a same-named ZIP. Run with the campaign EIC wrapper.
"""
import argparse
from ctypes import c_double
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import zipfile

MODELS = ('legacy', 'adaptive')
B_CELLS = [67, 263, 706, 775, 1478, 1538, 1991, 2051]
CASES = {'b1': B_CELLS, 'b2': B_CELLS, 'e1': [640, 1223], 'e2': [68, 1344]}
PURPOSE = {
    67: 'Weak/shifted B2 spectrum and matched B1 control',
    263: 'Two structures; adaptive missing in B2',
    706: 'Legacy numerical oscillations in B2',
    775: 'Low-ADC component plus higher peak in B2',
    1478: 'Low-ADC component plus higher peak in B2',
    1538: 'Relatively clean B1/B2 peak control',
    1991: 'Different legacy/adaptive fit ranges in B2',
    2051: 'Relatively clean B1/B2 peak control',
    640: 'Low-statistics E1 peak; legacy fit missing',
    1223: 'Distinct E1 peak; adaptive fit missing',
    68: 'Normal-looking E2 control',
    1344: 'Severe legacy oscillations in E2',
}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024*1024), b''): h.update(data)
    return h.hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def clean(value):
    x = float(value)
    return x if math.isfinite(x) else None


def histogram_number(value):
    """Keep exceptional values distinguishable in strict JSON and comparisons."""
    x = float(value)
    if math.isnan(x): return 'NaN'
    if math.isinf(x): return '+Infinity' if x > 0 else '-Infinity'
    return x


def one(directory, pattern):
    paths = list(directory.glob(pattern))
    if len(paths) != 1:
        raise ValueError(f'Expected exactly one {pattern} in {directory}; found {len(paths)}')
    return paths[0]


def hist_values(h):
    n = h.GetNbinsX()
    return dict(class_name=h.ClassName(), nbins=n, entries=histogram_number(h.GetEntries()),
                edges=[histogram_number(h.GetBinLowEdge(i)) for i in range(1,n+2)],
                contents=[histogram_number(h.GetBinContent(i)) for i in range(n+2)],
                errors=[histogram_number(h.GetBinError(i)) for i in range(n+2)],
                sumw2=[histogram_number(h.GetSumw2().At(i)) for i in range(h.GetSumw2N())],
                error_option=int(h.GetBinErrorOption()))


def histogram_issues(values):
    """Diagnose unusual data without changing the histogram being archived."""
    issues=[]
    for field in ('entries','edges','contents','errors','sumw2'):
        items=[values[field]] if field=='entries' else values[field]
        for index,value in enumerate(items):
            kind='nonfinite' if isinstance(value,str) else (
                'negative' if field!='edges' and value<0 else None)
            if kind is None: continue
            issue=dict(field=field,value=value,kind=kind)
            if field=='edges': issue['edge_index']=index
            elif field!='entries':
                issue['bin']=index
                issue['region']=('underflow' if index==0 else
                                 'overflow' if index==values['nbins']+1 else 'regular')
            issues.append(issue)
    return issues


def issue_summary(issues):
    counts={}
    for issue in issues:
        key=issue['field']+' '+issue['kind']
        counts[key]=counts.get(key,0)+1
    examples=[]
    for issue in issues[:4]:
        where=(f' bin {issue["bin"]} ({issue["region"]})' if 'bin' in issue else
               f' edge {issue["edge_index"]}' if 'edge_index' in issue else '')
        examples.append(f'{issue["field"]}{where}={issue["value"]}')
    return ', '.join(f'{key}: {count}' for key,count in counts.items())+'; '+', '.join(examples)


def fit_values(f):
    parameters = []
    for i in range(f.GetNpar()):
        lo, hi = c_double(), c_double()
        f.GetParLimits(i,lo,hi)
        parameters.append(dict(name=str(f.GetParName(i)),value=clean(f.GetParameter(i)),
                               error=clean(f.GetParError(i)),lower=clean(lo.value),upper=clean(hi.value)))
    return dict(title=str(f.GetTitle()), xmin=float(f.GetXmin()), xmax=float(f.GetXmax()),
                npx=int(f.GetNpx()), chi2=clean(f.GetChisquare()), ndf=int(f.GetNDF()),
                parameters=parameters,
                note='Stored TF1 is a record. Reconstruct evaluator from archived source before fitting.')


def copy_file(src, dest, records, expected=None):
    actual=digest(src)
    if expected is not None and actual != expected:
        raise ValueError('Archived source hash changed: '+str(src))
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dest)
    records.append(dict(source=str(src),output=str(dest),sha256=actual,size=dest.stat().st_size))


def log_excerpt(src, dest, cells):
    lines=src.read_text(errors='replace').splitlines()
    pattern=re.compile(r'(?:cell(?:\s+ID)?|CellID|cellID|Fit status HG)\s*:?\s*('
                       +'|'.join(map(str,cells))+r')(?!\d)',re.I)
    keep=set(range(min(100,len(lines))))
    hits=[]
    for i,line in enumerate(lines):
        if pattern.search(line):
            hits.append(i+1)
            keep.update(range(max(0,i-30),min(len(lines),i+16)))
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(''.join(f'{i+1}: {lines[i]}\n' for i in sorted(keep)))
    return dict(source=str(src),sha256=digest(src),original_lines=len(lines),
                matched_lines=hits,excerpt_lines=len(keep),
                note='Startup plus context around matching cell messages; absence of a message is not a success/failure verdict.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,default=Path('/gpfs01/star/scratch/pnord/lfhcal'))
    ap.add_argument('--out',type=Path,required=True,help='New directory; ZIP will be alongside it')
    args=ap.parse_args()
    import ROOT
    ROOT.gROOT.SetBatch(True)
    work=args.work.resolve();out=args.out.resolve();archive=out.with_name(out.name+'.zip')
    if out.exists() or archive.exists():
        ap.error('Use a new output path; preserving existing output')
    early=work/'adaptive-fullchains-20260928T223211Z'
    remaining=work/'adaptive-fullchains-remaining-20260929T014858Z'
    extension=work/'b2-r6-r8-20261001'
    # Preflight every selected histogram file and sidecar before creating output.
    selections=[]
    for dataset,cells in CASES.items():
        parent=remaining if dataset in ('b1','e2') else early
        stage='refine8' if dataset=='b2' else 'refine5'
        previous='refine7' if dataset=='b2' else 'refine4'
        root=extension if dataset=='b2' else parent
        for model in MODELS:
            directory=root/model/dataset/stage
            prior=root/model/dataset/previous
            spec=dict(dataset=dataset,model=model,cells=cells,parent=parent,root=root,
                      stage=stage,previous=previous,directory=directory,
                      hists=one(directory,'*_Hists.root'),current_calib=one(directory,'*_calib.txt'),
                      previous_calib=one(prior,'*_calib.txt'))
            for p in [parent/'source-hashes.json',parent/'manifest.json',
                      parent/f'build-{model}.json',directory/'cells.csv',directory/'stage.json']:
                if not p.is_file(): raise ValueError('Missing context: '+str(p))
            selections.append(spec)
    out.mkdir(parents=True)
    manifest=dict(format_version=2,created_by=Path(__file__).name,
        extraction_root_version=ROOT.gROOT.GetVersion(),fitting_performed=False,
        histogram_nonfinite_encoding='JSON strings NaN, +Infinity, -Infinity; original ROOT values preserved',
        selection=CASES,purposes={str(k):v for k,v in PURPOSE.items()},cases=[],files=[],campaigns={},warnings=[],
        controls_note='Normal-looking controls, not certified good calibrations. Selected deliberately, not a representative sample.',
        reproduction_note='Saved fits provide final parameters and limits, not original starts or a complete TFitResult. '
                          'Calibration tables, source, configuration, and log excerpts support reconstruction. '
                          'Compare original ROOT version and baseline before attributing changes to ranges.')
    # Copy archived first-party C++ and text configuration, never build products or event trees.
    for parent in sorted({s['parent'] for s in selections}):
        key=parent.name;target=out/'campaigns'/key
        hashes=json.loads((parent/'source-hashes.json').read_text())
        info=dict(path=str(parent),builds={});manifest['campaigns'][key]=info
        for name in ['manifest.json','source-hashes.json','adaptive_fulltests.py']:
            if (parent/name).is_file():copy_file(parent/name,target/name,manifest['files'])
        for model in MODELS:
            build=parent/f'build-{model}.json'
            info['builds'][model]=json.loads(build.read_text())
            copy_file(build,target/build.name,manifest['files'])
            source=parent/'sources'/model
            count=0
            for relative,expected in sorted(hashes[model].items()):
                rel=Path(relative)
                cpp=(len(rel.parts)==2 and rel.parts[0]=='NewStructure'
                     and rel.suffix in ('.h','.hh','.hpp','.cc','.cpp','.cxx'))
                config=relative.startswith('configs/TB2026/') and rel.suffix.lower() in ('.csv','.txt','.json','.yaml','.yml')
                if cpp or config:
                    copy_file(source/rel,target/'sources'/model/rel,manifest['files'],expected)
                    count+=1
            if not count:raise ValueError('No matching archived sources in '+str(source))
    if (extension/'extension.json').is_file():
        copy_file(extension/'extension.json',out/'b2-extension.json',manifest['files'])
    output=ROOT.TFile(str(out/'histograms.root'),'RECREATE')
    if not output or output.IsZombie():raise RuntimeError('Cannot create output ROOT file')
    verify=[]
    try:
        for s in selections:
            ds,model,stage=s['dataset'],s['model'],s['stage']
            print(f'Extracting {ds.upper()} {stage} {model}: {s["cells"]}',flush=True)
            target=out/'context'/ds/model
            for name,src in [('current-calibration.txt',s['current_calib']),
                             ('previous-calibration.txt',s['previous_calib']),
                             ('cells.csv',s['directory']/'cells.csv'),('stage.json',s['directory']/'stage.json')]:
                copy_file(src,target/name,manifest['files'])
            with (s['directory']/'cells.csv').open() as f:
                rows={int(r['cell_id']):r for r in csv.DictReader(f)}
            if (s['directory']/'DataPrep.log').is_file():
                log=log_excerpt(s['directory']/'DataPrep.log',target/'DataPrep-excerpt.log',s['cells'])
                dump(target/'log-excerpt.json',log)
            else:manifest['warnings'].append(f'{ds} {model}: DataPrep.log absent')
            file=ROOT.TFile.Open(str(s['hists']),'READ')
            if not file or file.IsZombie() or file.TestBit(ROOT.TFile.kRecovered):
                raise ValueError('Invalid input ROOT file: '+str(s['hists']))
            try:
                directory=file.Get('IndividualCellsTrigg')
                if not directory:raise ValueError('Missing triggered directory')
                for cell in s['cells']:
                    h=directory.Get(f'hspectramipTriggADCCellID{cell}')
                    fit=directory.Get(f'fmipmipTriggHGCellID{cell}')
                    if not h or not h.InheritsFrom('TH1') or h.GetDimension()!=1:
                        raise ValueError(f'{ds} {model} cell {cell}: no 1D triggered histogram')
                    if cell not in rows:raise ValueError('Cell absent from audit CSV: '+str(cell))
                    expected=str(rows[cell].get('fit_saved','')).lower() in ('true','1')
                    if bool(fit)!=expected:raise ValueError('CSV/ROOT saved-fit mismatch')
                    values=hist_values(h)
                    issues=histogram_issues(values)
                    if issues:
                        warning=f'{ds.upper()} {stage} {model} cell {cell}: '+issue_summary(issues)
                        manifest['warnings'].append(warning)
                        print('WARNING (preserved unchanged): '+warning,flush=True)
                    dest=output
                    for part in (ds,stage,model,'cell'+str(cell)):
                        dest=dest.GetDirectory(part) or dest.mkdir(part)
                    dest.cd();h.Write('spectrum')
                    if fit:fit.Write('saved_fit')
                    record=dict(dataset=ds,stage=stage,model=model,cell_id=cell,
                        purpose=PURPOSE[cell],campaign=s['parent'].name,
                        original_file=str(s['hists']),original_histogram=h.GetName(),
                        root_path=f'{ds}/{stage}/{model}/cell{cell}/spectrum',
                        audit_row=rows[cell],histogram=values,histogram_issues=issues,
                        fit=fit_values(fit) if fit else None)
                    manifest['cases'].append(record);verify.append(record)
            finally:file.Close()
    finally:output.Close()
    # Confirm that the small on-disk ROOT file preserves every bin/error and saved fit.
    reopened=ROOT.TFile.Open(str(out/'histograms.root'),'READ')
    try:
        for record in verify:
            h=reopened.Get(record['root_path'])
            if not h or hist_values(h)!=record['histogram']:
                raise ValueError('Output histogram verification failed: '+record['root_path'])
            f=reopened.Get(record['root_path'].rsplit('/',1)[0]+'/saved_fit')
            if bool(f)!=(record['fit'] is not None):raise ValueError('Output fit presence mismatch')
            if f and fit_values(f)!=record['fit']:raise ValueError('Output fit parameters/limits mismatch')
    finally:reopened.Close()
    manifest['histograms_root_sha256']=digest(out/'histograms.root')
    manifest['histogram_count']=len(verify)
    manifest['original_fit_count']=sum(r['fit'] is not None for r in verify)
    manifest['histograms_with_issues']=sum(bool(r['histogram_issues']) for r in verify)
    dump(out/'manifest.json',manifest)
    (out/'README.txt').write_text(
        'Frozen LFHCal range study: 20 dataset/cell cases, each with legacy-selected and adaptive-selected histograms.\n'
        'histograms.root contains original-bin TH1 spectra and saved TF1 records only; no event trees.\n'
        'manifest.json also includes every bin edge, count, error, entries and saved-fit parameters/limits.\n'
        'Raw Sumw2 and the bin-error option are included to diagnose invalid errors.\n'
        'Nonfinite histogram numbers use JSON strings NaN, +Infinity, -Infinity. ROOT values are unchanged.\n'
        'Per-case histogram_issues identifies every nonfinite or unexpected negative value, including flow bins.\n'
        'Extraction warnings require investigation before fitting; successful copying does not certify valid fit input.\n'
        'Do not evaluate a deserialized callback TF1 as the authoritative continuous model; rebuild from archived source.\n'
        'context/ contains current and previous calibrations, stage reports and available rejection-log excerpts.\n'
        'campaigns/ contains hash-checked first-party C++ source, configuration and original ROOT build versions.\n'
        'No fitting or calibration updates were performed. Source campaigns were opened read-only.\n'
        'Study exact baseline reproduction before range changes; missing fits do not establish why they were rejected.\n')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,str(Path(out.name)/p.relative_to(out)))
    size=archive.stat().st_size
    print(f'Verified {len(verify)} histograms and {manifest["original_fit_count"]} saved fits.',flush=True)
    if manifest['histograms_with_issues']:
        print(f'Preserved data warnings in {manifest["histograms_with_issues"]} histograms; see manifest.json.',flush=True)
    print(f'Upload: {archive}\nSize: {size/1024/1024:.2f} MiB',flush=True)
    if size>32*1024*1024:
        raise ValueError('Archive exceeds 32 MiB upload-tool limit; contact me before uploading')
    return 0


if __name__=='__main__':
    sys.exit(main())
