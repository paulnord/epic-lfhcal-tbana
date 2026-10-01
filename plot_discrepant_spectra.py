#!/usr/bin/env python3
"""Batch ROOT spectra review; original campaign evaluators, saved parameters, no refits.
Run inside the campaign's EIC shell (PyROOT required). No matplotlib dependency.
Defaults: B2 R8, E1/E2/E3 R5; all channels crossing any threshold or fit-save mismatch.
"""
import argparse
from array import array
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys

MODELS = ('legacy', 'adaptive')
PARAMS = ('scale_h', 'mpv', 'landau_width', 'gaussian_sigma')


def number(v):
    try:
        x = float(v)
        return x if math.isfinite(x) and x != -1000 else None
    except (TypeError, ValueError):
        return None


def saved(row, model):
    return str(row.get(model + '_fit_saved', '')).lower() in ('true', '1')


def select_rows(rows, limits):
    ranked = []
    for row in rows:
        reasons, score = [], 0.
        both = all(saved(row, m) for m in MODELS)
        if saved(row, 'legacy') != saved(row, 'adaptive'):
            reasons.append('fit saved by only one method')
            score = 1e6
        if both:
            for key, limit in zip(PARAMS, limits):
                a, b = (number(row.get(m + '_' + key)) for m in MODELS)
                if a is None or b is None:
                    continue
                # Symmetric fractional difference: neither method is the reference.
                diff = abs(a-b)/max((abs(a)+abs(b))/2, .1)
                score = max(score, diff/limit)
                if diff >= limit:
                    reasons.append(f'{key}: {100*diff:.2f}% symmetric difference')
        if reasons:
            ranked.append(dict(row, reason='; '.join(reasons), score=score))
    return sorted(ranked, key=lambda r: (-r['score'], int(r['cell_id'])))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def requested_rows(rows, cells):
    by_cell = {int(r['cell_id']): r for r in rows}
    missing = sorted(set(cells) - set(by_cell))
    if missing:
        raise ValueError('Requested cells absent from report: ' + str(missing))
    return [dict(by_cell[cell], reason='Requested matching cell; difference thresholds bypassed', score=0.)
            for cell in dict.fromkeys(cells)]


def checked_source(parent, model, relative):
    path = parent/'sources'/model/relative
    expected = json.loads((parent/'source-hashes.json').read_text())[model][relative]
    if sha(path) != expected:
        raise ValueError('Archived source changed: ' + str(path))
    return path


def extract_legacy(source):
    match = re.search(r'double TileSpectra::langaufun\(double \*x, double \*par\)\s*\{', source)
    if not match:
        raise ValueError('Unrecognized legacy evaluator signature')
    # Reviewed source boundary, without copying the rest of TileSpectra.
    end = source.index('int TileSpectra::langaupro(', match.end())
    body = source[match.start():end].strip()
    if not body.endswith('}'):
        raise ValueError('Unexpected evaluator boundary')
    return body.replace('TileSpectra::langaufun', 'legacy', 1)


def declare_evaluators(ROOT, parent, namespace, header_hash):
    legacy = checked_source(parent, 'legacy', 'NewStructure/TileSpectra.cc')
    adaptive = checked_source(parent, 'adaptive', 'NewStructure/TileSpectra.cc')
    header = checked_source(parent, 'adaptive', 'NewStructure/AdaptiveLangau.h')
    if header_hash is not None and sha(header) != header_hash:
        raise ValueError('Campaigns use different adaptive headers; run separately')
    source = adaptive.read_text()
    expression = re.search(r'return lfhcal::adaptive_langau::Convolution\([\s\S]*?\}\)\(x\[0\]\);', source)
    if not expression or 'model = +[](double* x, double* p)' not in source:
        raise ValueError('Unrecognized adaptive evaluator; refusing to substitute a model')
    declaration = '#include <TMath.h>\n#include <vector>\n#include <cmath>\n#include <stdexcept>\n'
    if header_hash is None:
        declaration += '#include ' + json.dumps(str(header)) + '\n'
    declaration += 'namespace ' + namespace + ' {\n' + extract_legacy(legacy.read_text())
    declaration += '\ndouble adaptive(double *x, double *p) {' + expression.group() + '}\n'
    declaration += '''
std::vector<double> sample(bool useAdaptive, double lo, double hi, int n,
                           const std::vector<double>& parameters) {
  auto p=parameters; std::vector<double> y; y.reserve(n);
  for (int i=0;i<n;++i) {
    double x=lo+(hi-lo)*i/(n-1.);
    double v=useAdaptive ? adaptive(&x,p.data()) : legacy(&x,p.data());
    if (!std::isfinite(v) || v<0) throw std::runtime_error("Invalid curve evaluation");
    y.push_back(v);
  }
  return y;
}
}\n'''
    if not ROOT.gInterpreter.Declare(declaration):
        raise RuntimeError('Could not compile archived evaluators')
    return sha(header), dict(legacy=str(legacy), adaptive=str(adaptive), header=str(header),
                            legacy_sha256=sha(legacy), adaptive_sha256=sha(adaptive),
                            header_sha256=sha(header))


def read_channel(ROOT, file, cell):
    directory = file.Get('IndividualCellsTrigg')
    if not directory:
        raise ValueError('Missing IndividualCellsTrigg in ' + file.GetName())
    h = directory.Get(f'hspectramipTriggADCCellID{cell}')
    fit = directory.Get(f'fmipmipTriggHGCellID{cell}')
    result = {'hist': h, 'fit': fit}
    if fit:
        result.update(parameters=[float(fit.GetParameter(i)) for i in range(4)],
                      xmin=float(fit.GetXmin()), xmax=float(fit.GetXmax()))
    return result


def curve(ROOT, namespace, model, data, max_points):
    p = data['parameters']
    lo, hi = data['xmin'], data['xmax']
    if not (hi > lo and p[0] > 0 and p[3] > 0):
        raise ValueError('Invalid stored parameters or range')
    h = data['hist']
    binwidth = min(h.GetBinWidth(i) for i in range(1,h.GetNbinsX()+1)) if h else 1.
    step = min(binwidth/10, max(p[0], p[3])/60)
    if model == 'legacy' and p[0] < p[3]/10:
        step = min(step, p[0]/16, p[3]/160)
    n = max(2001, math.ceil((hi-lo)/step)+1)
    if n > max_points:
        raise ValueError(f'Curve needs {n} samples; increase --max-points (no coarse fallback)')
    values = list(getattr(ROOT, namespace).sample(model == 'adaptive', lo, hi, n, p))
    x = array('d', (lo+(hi-lo)*i/(n-1) for i in range(n)))
    graph = ROOT.TGraph(n, x, array('d', values))
    graph.SetLineColor(ROOT.kOrange+7 if model == 'legacy' else ROOT.kAzure+2)
    graph.SetLineWidth(2)
    data.update(graph=graph, curve_x=x, curve_y=values, samples=n, sample_step=(hi-lo)/(n-1))


def label(ROOT, text, x=.14, y=.87, size=.033):
    obj = ROOT.TLatex()
    obj.SetNDC(); obj.SetTextSize(size)
    obj.DrawLatex(x,y,text)
    return obj


def draw_page(ROOT, dataset, stage, row, data, destination, pdf, wiggle=False):
    cell = int(row['cell_id'])
    fits = [d for d in data.values() if d.get('fit')]
    histograms = [d['hist'] for d in data.values() if d.get('hist')]
    if not histograms:
        raise ValueError('Neither method has a histogram')
    lo = min((d['xmin'] for d in fits), default=0.)
    hi = max((d['xmax'] for d in fits), default=200.)
    overview_lo = min(0.,lo)
    overview_hi = hi*1.15 if hi > 0 else hi+10
    canvas = ROOT.TCanvas('review', 'Spectra review', 1500, 550 if wiggle else 1000)
    canvas.Divide(2,1 if wiggle else 2, .005,.005)
    keep = []
    for band in range(1 if wiggle else 2):
        left, right = (overview_lo,overview_hi) if band == 0 else (lo,hi)
        if wiggle:
            p = data['legacy']['parameters']
            center = min(max(p[1],lo),hi)
            span = max(2*p[3]/10, 8*p[0])
            left, right = max(lo,center-span), min(hi,center+span)
        maximum = 0.
        for d in data.values():
            h = d.get('hist')
            if h:
                maximum = max(maximum, max((h.GetBinContent(i)+h.GetBinError(i)
                    for i in range(1,h.GetNbinsX()+1) if left <= h.GetBinCenter(i) <= right), default=0.))
            maximum = max(maximum, max((y for x,y in zip(d.get('curve_x',[]), d.get('curve_y',[]))
                                      if left <= x <= right), default=0.))
        for col, model in enumerate(MODELS):
            pad = canvas.cd(1+col+2*band)
            pad.SetLeftMargin(.12); pad.SetBottomMargin(.12); pad.SetTopMargin(.19)
            log = band == 0 and not wiggle
            pad.SetLogy(log)
            d = data[model]
            frame = pad.DrawFrame(left, .3 if log else 0., right, max(2.,maximum)*(4 if log else 1.2))
            frame.SetTitle(f'{dataset.upper()} cell {cell} | {stage} | {model};ADC;Counts / original bin')
            keep.append(frame)
            h = d.get('hist')
            if h:
                h.SetStats(False); h.SetMarkerStyle(20); h.SetMarkerSize(.35)
                h.SetLineColor(ROOT.kBlack); h.Draw('E SAME')
            else:
                keep.append(label(ROOT, 'Histogram absent'))
            if d.get('graph'):
                d['graph'].Draw('L SAME')
            for boundary in (d.get('xmin'),d.get('xmax')):
                if boundary is not None and left <= boundary <= right:
                    line = ROOT.TLine(boundary,.3 if log else 0,boundary,max(2.,maximum)*1.15)
                    line.SetLineStyle(3); line.SetLineColor(ROOT.kGray+1); line.Draw(); keep.append(line)
            if d.get('fit'):
                p = d['parameters']; f = d['fit']
                scale = number(row.get(model+'_scale_h'))
                scale_text = '?' if scale is None else f'{scale:.5g}'
                text = f'H={scale_text}  MPV={p[1]:.4g}  wL={p[0]:.4g}  sigma={p[3]:.4g}'
                keep.append(label(ROOT,text,y=.93,size=.030))
                chi = f.GetChisquare()/f.GetNDF() if f.GetNDF()>0 else float('nan')
                keep.append(label(ROOT,f'entries={h.GetEntries():.0f}  chi2/ndf={chi:.3g}' if h else f'chi2/ndf={chi:.3g}',y=.88,size=.03))
            else:
                keep.append(label(ROOT,'NO SAVED FIT (no curve reconstructed)',y=.93,size=.032))
            if d.get('error'):
                keep.append(label(ROOT,'CURVE ERROR: see index.html',y=.83,size=.032))
            if band == 1 or wiggle:
                keep.append(label(ROOT,'Wiggle zoom (display only; no refit)' if wiggle else 'Fit region (linear scale)',y=.83,size=.03))
    canvas.Print(str(destination)); canvas.Print(str(pdf))
    canvas.Close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,default=Path('/gpfs01/star/scratch/pnord/lfhcal'))
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--datasets',nargs='+',choices=('b1','b2','e1','e2','e3'),default=['b2','e1','e2','e3'])
    ap.add_argument('--cells',nargs='+',type=int,help='Plot these cells regardless of method differences')
    ap.add_argument('--h-threshold',type=float,default=.01)
    ap.add_argument('--mpv-threshold',type=float,default=.05)
    ap.add_argument('--width-threshold',type=float,default=.25)
    ap.add_argument('--max-per-set',type=int,default=0,help='0: all selected; otherwise highest ranked N')
    ap.add_argument('--max-points',type=int,default=1000000)
    args = ap.parse_args()
    limits = [args.h_threshold,args.mpv_threshold,args.width_threshold,args.width_threshold]
    if min(limits)<=0 or args.max_per_set<0 or args.max_points<2001:
        ap.error('Thresholds must be positive, max-per-set >=0 and max-points >=2001')
    import ROOT
    ROOT.gROOT.SetBatch(True); ROOT.gStyle.SetOptStat(0); ROOT.gStyle.SetOptTitle(1)
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        ap.error('Use an empty output directory; preserving existing review')
    out.mkdir(parents=True,exist_ok=True)
    work = args.work.resolve()
    early = work/'adaptive-fullchains-20260928T223211Z'
    remaining = work/'adaptive-fullchains-remaining-20260929T014858Z'
    extension = work/'b2-r6-r8-20261001'
    metadata = dict(thresholds=dict(zip(PARAMS,limits)),
        selection='abs(A-L)/max((abs(A)+abs(L))/2,0.1); either saved-fit mismatch also included',
        refit=False, histogram_normalization='none; original bins and counts',
        root_version=ROOT.gROOT.GetVersion(), datasets={}, errors=[])
    if args.cells:
        metadata['selection'] = 'Explicit requested cells; difference thresholds bypassed'
        metadata['requested_cells'] = args.cells
    gallery = ['<!doctype html><meta charset="utf-8"><title>Discrepant LFHCal spectra</title>',
        '<style>body{font:16px sans-serif;margin:2em}img{max-width:100%}section{margin:3em 0}code{overflow-wrap:anywhere}</style>',
        '<h1>LFHCal spectra review</h1><p>Original bins; no refits. Curves evaluated from archived source with saved parameters. '
        'Top: logarithmic overview. Bottom: linear fit region. Dotted lines: fit limits. '
        'Both methods share axes. Their selected histograms can differ.</p>',
        f'<p>Selection: H ≥{100*limits[0]:g}%, MPV ≥{100*limits[1]:g}%, either width ≥{100*limits[2]:g}%, or only one saved fit. '
        'Exact configured thresholds and all candidate rankings: <a href="manifest.json">manifest</a>.</p>']
    if args.cells:
        gallery[-1] = '<p>Explicit matching cells: ' + ', '.join(map(str,args.cells)) + '. Difference thresholds bypassed. <a href="manifest.json">Manifest</a>.</p>'
    header_hash = None
    errors = []
    for index, dataset in enumerate(args.datasets):
        parent = remaining if dataset in ('b1','e2') else early
        root = extension if dataset == 'b2' else parent
        stage = 'refine8' if dataset == 'b2' else 'refine5'
        report = root/'reports'/f'{dataset}-comparison.csv'
        with report.open() as stream:
            rows = [r for r in csv.DictReader(stream) if r['stage']==stage]
        if not rows:
            raise ValueError('No rows for '+dataset+' '+stage)
        candidates = requested_rows(rows,args.cells) if args.cells else select_rows(rows,limits)
        chosen = candidates[:args.max_per_set] if args.max_per_set else candidates
        print(f'{dataset.upper()} {stage}: {len(candidates)} candidates, plotting {len(chosen)}',flush=True)
        meta = dict(stage=stage, report=str(report), report_sha256=sha(report),
                    candidates=len(candidates), plotted=len(chosen), root_files={}, channels=[])
        metadata['datasets'][dataset] = meta
        with (out/f'{dataset}-selection.csv').open('w',newline='') as stream:
            fields = list(rows[0]) + ['reason','score','plotted']
            writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
            chosen_ids={r['cell_id'] for r in chosen}
            writer.writerows(dict(r,plotted=r['cell_id'] in chosen_ids) for r in candidates)
        gallery.append(f'<h2>{dataset.upper()} {stage}: {len(chosen)} of {len(candidates)} candidates</h2>'
                       f'<p><a href="{dataset}-selection.csv">All candidate rankings</a></p>')
        if not chosen:
            continue
        namespace = 'spectra_review_'+str(index)
        header_hash, meta['source'] = declare_evaluators(ROOT,parent,namespace,header_hash)
        files = {}
        for model in MODELS:
            matches = list((root/model/dataset/stage).glob('*_Hists.root'))
            if len(matches)!=1:
                raise ValueError('Expected exactly one hist file in '+str(root/model/dataset/stage))
            file=ROOT.TFile.Open(str(matches[0]),'READ')
            if not file or file.IsZombie() or file.TestBit(ROOT.TFile.kRecovered):
                raise ValueError('Invalid ROOT file: '+str(matches[0]))
            files[model] = file
            meta['root_files'][model] = str(matches[0])
        pdf = out/f'{dataset}-spectra.pdf'
        book = ROOT.TCanvas('book','book',10,10); book.Print(str(pdf)+'[')
        gallery.append(f'<p><a href="{pdf.name}">PDF book</a></p>')
        try:
            for position,row in enumerate(chosen,1):
                cell=int(row['cell_id']); print(f'  {position}/{len(chosen)} cell {cell}',flush=True)
                data={m:read_channel(ROOT,files[m],cell) for m in MODELS}
                channel=dict(cell_id=cell,reason=row['reason'],same_histogram=row['same_histogram'],models={})
                meta['channels'].append(channel)
                for model,d in data.items():
                    if bool(d['fit']) != saved(row,model):
                        raise ValueError(f'{dataset} {cell} {model}: CSV/ROOT fit mismatch')
                    if d['fit']:
                        for key,actual in zip(('landau_width','mpv',None,'gaussian_sigma'),d['parameters']):
                            expected=number(row.get(model+'_'+key)) if key else None
                            if key and (expected is None or not math.isclose(expected,actual,rel_tol=1e-10,abs_tol=1e-10)):
                                raise ValueError(f'{dataset} {cell}: CSV/ROOT parameter mismatch')
                        try:
                            curve(ROOT,namespace,model,d,args.max_points)
                        except Exception as exc:
                            d['error']=str(exc)
                            errors.append(f'{dataset} {cell} {model}: {exc}')
                    channel['models'][model]={k:d[k] for k in ('parameters','xmin','xmax','samples','sample_step','error') if k in d}
                name=f'{dataset}-{stage}-cell{cell}.png'
                draw_page(ROOT,dataset,stage,row,data,out/name,pdf)
                gallery.append(f'<section><h3>{dataset.upper()} cell {cell}</h3><p>{html.escape(row["reason"])}; '
                               f'identical histograms: {html.escape(row["same_histogram"])}.</p><img loading="lazy" src="{name}">')
                # A narrow extra view avoids compressing real fixed-grid oscillations into pixels.
                d=data['legacy']
                if d.get('graph') and d['parameters'][0] < d['parameters'][3]/10:
                    zoom=f'{dataset}-{stage}-cell{cell}-wiggle-zoom.png'
                    draw_page(ROOT,dataset,stage,row,data,out/zoom,pdf,wiggle=True)
                    gallery.append(f'<p>Fine view: legacy Landau width is smaller than its convolution grid spacing.</p>'
                                   f'<img loading="lazy" src="{zoom}">')
                for model,d in data.items():
                    if d.get('error'):
                        gallery.append('<p><strong>'+html.escape(model+': '+d['error'])+'</strong></p>')
                gallery.append('</section>')
        finally:
            book.Print(str(pdf)+']'); book.Close()
            for file in files.values(): file.Close()
        metadata['errors']=errors
        (out/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
        (out/'index.html').write_text('\n'.join(gallery))
    metadata['errors']=errors
    (out/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (out/'index.html').write_text('\n'.join(gallery))
    print('Review:',out/'index.html',flush=True)
    if errors:
        print(f'{len(errors)} curve errors recorded; affected panels explicitly marked.',file=sys.stderr)
        return 2
    return 0


if __name__=='__main__':
    sys.exit(main())
