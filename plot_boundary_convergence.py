#!/usr/bin/env python3
"""Four-way boundary study plots, using saved report tables only (no ROOT).

One parameter per figure; panels are Legacy/Adaptive x original/valley.
All-set flow plots show step changes and a fixed original Legacy R5 reference.
Per-set absolute plots use shared linear axes. Missing/newly-unsaved fits are
NaN gaps. Reused MIP is labelled explicitly. Requires numpy and matplotlib.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

PARAMETERS = [('scale_h', 'H'), ('mpv', 'MPV'),
              ('landau_width', 'Landau width'), ('gaussian_sigma', 'Gaussian sigma')]
ARMS = [('legacy', 'original'), ('legacy', 'valley'),
        ('adaptive', 'original'), ('adaptive', 'valley')]
DATASETS = 'b1 b2 c1 c2 c3 d1 d2 e1 e2 e3 f1 f2 g1 g2'.split()


def number(s):
    try:
        v = float(s)
        return v if math.isfinite(v) and v != -1000 else np.nan
    except (ValueError, TypeError):
        return np.nan


def flag(s):
    s = str(s).strip().lower()
    if s not in ('true', 'false', '1', '0'):
        raise ValueError('Invalid saved flag: ' + s)
    return s in ('true', '1')


def read(path, ds):
    data = {}
    with path.open(newline='') as f:
        reader = csv.DictReader(f)
        required = {'dataset', 'stage', 'model', 'cell_id', 'execution_origin'}
        required |= {a + '_' + p for a in ('original', 'valley')
                     for p in ['saved'] + [p for p, _ in PARAMETERS]}
        if required - set(reader.fieldnames or []):
            raise ValueError(str(path) + ': missing required columns')
        for row in reader:
            if row['dataset'] != ds or row['model'] not in ('legacy', 'adaptive'):
                raise ValueError(str(path) + ': unexpected dataset/model')
            stage = row['stage']
            if stage == 'select':
                continue
            n = 0 if stage == 'mip' else int(stage.removeprefix('refine'))
            for boundary in ('original', 'valley'):
                key = (row['model'], boundary, int(row['cell_id']), n)
                if key in data:
                    raise ValueError(str(path) + ': duplicate ' + str(key))
                saved = flag(row[boundary + '_saved'])
                data[key] = {p: number(row[boundary + '_' + p]) if saved else np.nan
                             for p, _ in PARAMETERS}
    last = 8 if ds == 'b2' else 5
    for model, boundary in ARMS:
        stages = {n for m, b, c, n in data if (m, b) == (model, boundary)}
        if stages != set(range(last + 1)):
            raise ValueError('%s %s %s: incomplete stages %s' % (ds, model, boundary, stages))
    return data, last


def value(data, arm, cell, n, parameter):
    return data.get((*arm, cell, n), {}).get(parameter, np.nan)


def series(data, arm, cell, ns, p, mode):
    ys = []
    for n in ns:
        current = value(data, arm, cell, n, p)
        if mode == 'absolute':
            ys.append(current)
        else:
            ref = (value(data, arm, cell, n-1, p) if mode == 'step'
                   else value(data, ('legacy', 'original'), cell, 5, p))
            ys.append((current-ref)/abs(ref) if np.isfinite(ref) and ref != 0 else np.nan)
    return np.array(ys)


def color(cell):
    return plt.get_cmap('turbo')((cell * .6180339887498949) % 1)


def save(fig, out, name, pdf):
    fig.savefig(out / (name + '.png'), dpi=150)
    if pdf:
        fig.savefig(out / (name + '.pdf'))
    plt.close(fig)
    print(name, flush=True)


def plots(all_data, lasts, args):
    exported = []
    names = []
    for p, title in PARAMETERS:
        for mode in ('step', 'legacy-r5'):
            fig, axs = plt.subplots(2, 2, figsize=(15, max(7, .6*len(all_data)+4)),
                                    sharex=True, sharey=True)
            clipped = 0
            for ax, arm in zip(axs.flat, ARMS):
                for lane, (ds, data) in enumerate(all_data.items(), 1):
                    ns = np.arange(1 if mode == 'step' else 0, lasts[ds]+1)
                    tracks = []
                    ax.axhline(lane, color='0.6', lw=.5)
                    for cell in sorted({c for m, b, c, n in data}):
                        ys = series(data, arm, cell, ns, p, mode)
                        q = np.sign(ys)*np.log10(1+np.abs(ys)/args.r0)
                        hit = np.isfinite(q) & (np.abs(q)>args.clip)
                        clipped += int(hit.sum())
                        scaled = lane - .42*np.clip(q, -args.clip, args.clip)/args.clip
                        ax.plot(ns, scaled, color=color(cell), alpha=.18, lw=.6, marker='.', ms=2)
                        for sign, marker in ((1, '^'), (-1, 'v')):
                            mask = hit & (np.sign(q)==sign)
                            ax.scatter(ns[mask], scaled[mask], marker=marker, s=9, color=color(cell))
                        tracks.append(q)
                        for n, y in zip(ns, ys):
                            exported.append(dict(dataset=ds, method=arm[0], boundary=arm[1],
                                cell_id=cell, parameter=p, stage=int(n), view=mode,
                                fractional_change=float(y) if np.isfinite(y) else '',
                                clipped=bool(np.isfinite(y) and math.log10(1+abs(y)/args.r0)>args.clip)))
                    for i, n in enumerate(ns):
                        vals = np.array(tracks)[:, i]
                        vals = vals[np.isfinite(vals)]
                        if len(vals):
                            lo, med, hi = np.quantile(vals, [.16, .5, .84])
                            points = lane-.42*np.clip([lo, med, hi], -args.clip, args.clip)/args.clip
                            ax.plot([n, n], [points[0], points[2]], color='black', alpha=.5, lw=2)
                            ax.plot(n, points[1], 'k.', ms=4)
                    # Small signed percentage ruler at the left of every lane.
                    for fraction in (.01,):
                        q = math.log10(1+fraction/args.r0)
                        if q <= args.clip:
                            for sign in (-1, 1):
                                y = lane-sign*.42*q/args.clip
                                ax.text(ns[0]-.18, y, '%+.0f%%' % (100*sign*fraction),
                                        fontsize=5, ha='right', va='center')
                ax.set_title('%s / %s boundary' % (arm[0].capitalize(), arm[1]))
                ax.set_yticks(range(1,len(all_data)+1), [d.upper() for d in all_data])
                ax.set_ylim(len(all_data)+.55, .45)
                start = 1 if mode == 'step' else 0
                ax.set_xlim(start-.8, max(lasts.values())+.3)
                ax.set_xticks(range(start,max(lasts.values())+1),
                              [('MIP*' if n==0 else 'R%d'%n) for n in range(start,max(lasts.values())+1)])
                ax.tick_params(labelleft=True, labelbottom=True)
                ax.grid(axis='x', alpha=.15)
            desc = 'Consecutive-fit fractional change' if mode=='step' else 'Relative to the same cell\'s original Legacy R5'
            fig.suptitle(title + ' — ' + desc, fontsize=15)
            fig.text(.5,.018,'Saved fits only; missing endpoints are gaps. Black: median and central 68%%. '
                     'Triangles: clipped values (%d).\nSigned log: sign(r) log10(1+|r|/%g); limit ±%g. '
                     'MIP* reused; R1 step is relative to MIP. Only B2 extends past R5.' % (clipped,args.r0,args.clip),
                     ha='center',fontsize=8)
            fig.tight_layout(rect=(0,.065,1,.96))
            name = 'flow-%s-%s' % (p,mode)
            save(fig,args.out,name,args.pdf)
            names.append(name)
        for ds, data in all_data.items():
            fig, axs = plt.subplots(2,2,figsize=(12,8),sharex=True,sharey=True)
            ns = np.arange(lasts[ds]+1)
            for ax, arm in zip(axs.flat,ARMS):
                count = 0
                for cell in sorted({c for m,b,c,n in data}):
                    ys = series(data,arm,cell,ns,p,'absolute')
                    count += int(np.isfinite(ys).sum())
                    ax.plot(ns,ys,color=color(cell),alpha=.25,lw=.7,marker='.',ms=2)
                if not count:
                    ax.text(.5,.5,'No saved finite values',transform=ax.transAxes,ha='center')
                ax.set_title('%s / %s boundary'% (arm[0].capitalize(),arm[1]))
                ax.set_ylabel(title+' (ADC)')
                ax.set_xticks(ns,['MIP*']+['R%d'%n for n in ns[1:]])
                ax.tick_params(labelbottom=True,labelleft=True)
                ax.grid(alpha=.2)
            fig.suptitle(ds.upper()+' — absolute '+title)
            fig.text(.5,.02,'Shared linear scales; same cell colors. Saved fits only; gaps are not bridged. MIP* reused.',ha='center',fontsize=9)
            fig.tight_layout(rect=(0,.05,1,.95))
            name = '%s-absolute-%s'%(ds,p)
            save(fig,args.out,name,args.pdf)
            names.append(name)
    with (args.out/'flow-values.csv').open('w',newline='') as f:
        w = csv.DictWriter(f,fieldnames=list(exported[0]))
        w.writeheader()
        w.writerows(exported)
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--datasets',nargs='+',default=DATASETS)
    ap.add_argument('--pdf',action='store_true')
    ap.add_argument('--r0',type=float,default=1e-4)
    ap.add_argument('--clip',type=float,default=4)
    args = ap.parse_args()
    if not (math.isfinite(args.r0) and args.r0>0 and math.isfinite(args.clip) and args.clip>0):
        ap.error('r0 and clip must be finite and positive')
    data, lasts, sources = {}, {}, {}
    # Preflight all datasets before producing any plots; incomplete B2 fails here.
    for ds in args.datasets:
        if ds not in DATASETS or ds in data:
            ap.error('Unknown or duplicate dataset: '+ds)
        path = args.root/'reports'/(ds+'-boundary-comparison.csv')
        data[ds], lasts[ds] = read(path,ds)
        sources[ds] = dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    stats = args.root/'all-stage-statistics.csv'
    if not stats.is_file():
        ap.error('Campaign summary is not ready: missing '+str(stats))
    args.out.mkdir(parents=True,exist_ok=True)
    names = plots(data,lasts,args)
    shutil.copyfile(stats,args.out/stats.name)
    (args.out/'sources.json').write_text(json.dumps(dict(sources=sources,r0=args.r0,clip=args.clip,
        fixed_reference='original Legacy R5 saved fit',reused_stage='MIP',
        statistics_sha256=hashlib.sha256(stats.read_bytes()).hexdigest()),indent=2)+'\n')
    (args.out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Boundary comparison</title>'
        '<h1>Boundary comparison</h1><p>Original / valley boundary × Legacy / Adaptive. '
        'MIP is reused. Triangles mark clipping, not failed fits.</p>'+
        ''.join('<p><a href="%s.png">%s</a></p>'%(n,n) for n in names))
    bundle = args.out.with_name(args.out.name+'.zip')
    files = [args.out/(n+ext) for n in names for ext in (['.png','.pdf'] if args.pdf else ['.png'])]
    files += [args.out/n for n in ('flow-values.csv','all-stage-statistics.csv','sources.json','index.html')]
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for path in files:
            z.write(path,path.name)
    print('Download:',bundle)


if __name__ == '__main__':
    main()
