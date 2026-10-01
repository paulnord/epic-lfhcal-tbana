#!/usr/bin/env python3
"""Fit-parameter Nord plots from full-chain *-comparison.csv reports.

Produces four 2x2 figures (step and fixed legacy-R5 reference, each method)
and an absolute B2 parameter figure. New-fit flags are required for every
plotted value, including ScaleH. Missing fits produce gaps, never interpolation.
Step fractions divide by the absolute preceding value; fixed-reference fractions
divide by the absolute legacy R5 value. Zero denominators are undefined and
omitted; the absolute plot still shows zero values. The signed-log map is
sign(r)*log10(1+abs(r)/r0). Clipping is marked with triangles and counted.

Repeat --root for disjoint campaigns. --replace-report explicitly replaces one
dataset with a completed extension report (e.g. B2 through R8). Requires numpy
and matplotlib, not ROOT. CSVs retain unclipped values and source provenance.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import re

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PARAMETERS = [('scale_h', 'ScaleH'), ('mpv', 'MPV'),
              ('landau_width', 'Landau width'), ('gaussian_sigma', 'Gaussian σ')]
MODELS = ('legacy', 'adaptive')


def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) and x != -1000 else None
    except (ValueError, TypeError):
        return None


def stage_index(stage):
    if stage == 'mip':
        return 0
    match = re.fullmatch(r'refine([1-9][0-9]*)', stage)
    return int(match[1]) if match else None


def label(n):
    return 'MIP' if n == 0 else f'R{n}'


def read_report(path):
    data = {}
    with path.open(newline='') as f:
        reader = csv.DictReader(f)
        required = {'stage', 'cell_id'} | {f'{m}_{p}' for m in MODELS
                    for p in ['fit_saved'] + [p for p, _ in PARAMETERS]}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'{path}: missing columns {sorted(missing)}')
        for row in reader:
            n = stage_index(row['stage'])
            if n is None:
                continue
            cell = int(row['cell_id'])
            for model in MODELS:
                key = (model, cell, n)
                if key in data:
                    raise ValueError(f'{path}: duplicate row {key}')
                flag = row[f'{model}_fit_saved'].lower().strip()
                if flag not in ('true', 'false', '1', '0'):
                    raise ValueError(f'{path}: invalid fit_saved flag {flag!r}')
                saved = flag in ('true', '1')
                data[key] = {p: number(row[f'{model}_{p}']) if saved else None
                             for p, _ in PARAMETERS}
    if not data:
        raise ValueError(f'{path}: empty report')
    return data


def load(roots, replacements):
    data, sources = {}, {}
    for root in roots:
        paths = sorted((root/'reports').glob('*-comparison.csv'))
        if not paths:
            raise ValueError(f'No comparison reports under {root}/reports')
        for path in paths:
            dataset = path.name.removesuffix('-comparison.csv').lower()
            if dataset in data:
                raise ValueError(f'Duplicate dataset {dataset}; use --replace-report explicitly')
            data[dataset], sources[dataset] = read_report(path), str(path.resolve())
    for path in replacements:
        dataset = path.name.removesuffix('-comparison.csv').lower()
        if dataset not in data:
            raise ValueError(f'Replacement has no original dataset: {dataset}')
        data[dataset], sources[dataset] = read_report(path), str(path.resolve())
    return data, sources


def value(data, model, cell, n, parameter):
    return data.get((model, cell, n), {}).get(parameter)


def measures(data, datasets, max_stage, r0, clip):
    rows = []
    for ds in datasets:
        cells = sorted({cell for _, cell, _ in data[ds]})
        for model in MODELS:
            for cell in cells:
                for p, _ in PARAMETERS:
                    for n in range(max_stage + 1):
                        current = value(data[ds], model, cell, n, p)
                        if current is None:
                            continue
                        for mode in ('step', 'legacy-r5'):
                            if mode == 'step' and n == 0:
                                continue
                            previous = (value(data[ds], model, cell, n-1, p)
                                        if mode == 'step' else
                                        value(data[ds], 'legacy', cell, 5, p))
                            valid = previous is not None and previous != 0
                            delta = current - previous if previous is not None else None
                            fraction = delta / abs(previous) if valid else None
                            q = math.copysign(math.log10(1+abs(fraction)/r0), fraction) if valid else None
                            rows.append(dict(dataset=ds, model=model, cell_id=cell,
                                parameter=p, stage=label(n), stage_index=n, view=mode,
                                value=current, reference=previous, delta_adc=delta,
                                fractional_change=fraction, signed_log=q,
                                plotted_q=max(-clip, min(clip, q)) if valid else None,
                                clipped=bool(valid and abs(q)>clip), valid_pair=valid))
    return rows


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def cell_color(cell):
    # Deterministic across parameters, datasets, and methods; independent of gaps.
    return plt.get_cmap('turbo')((cell * 0.6180339887498949) % 1)


def save(fig, path, pdf):
    fig.savefig(str(path)+'.png', dpi=180)
    print(str(path)+'.png')
    if pdf:
        fig.savefig(str(path)+'.pdf')
    plt.close(fig)


def nord(rows, datasets, model, mode, last, args):
    fig, axs = plt.subplots(2, 2, figsize=(16, max(10, 1.15*len(datasets)+4)),
                            sharex=True, sharey=True)
    ns = list(range(1 if mode == 'step' else 0, last+1))
    labels = [f'{label(n-1)}→{label(n)}' if mode == 'step' else label(n) for n in ns]
    scale = .43/args.clip
    clipped_total = 0
    for ax, (p, title) in zip(axs.flat, PARAMETERS):
        selected = [r for r in rows if r['model']==model and r['view']==mode
                    and r['parameter']==p and r['valid_pair']]
        for lane, ds in enumerate(datasets, 1):
            tracks = {}
            ax.axhline(lane, color='black', lw=.65, alpha=.4)
            for r in selected:
                if r['dataset']==ds:
                    tracks.setdefault(r['cell_id'], {})[r['stage_index']] = r
            for cell, track in sorted(tracks.items()):
                # Positive changes point UP, matching the signed ruler.
                ys = [lane-scale*track[n]['plotted_q'] if n in track else np.nan for n in ns]
                ax.plot(ns, ys, color=cell_color(cell), alpha=args.alpha,
                        lw=.65, marker='.', markersize=1.8)
                for n in ns:
                    if n in track and track[n]['clipped']:
                        clipped_total += 1
                        r=track[n]
                        ax.plot(n, lane-scale*r['plotted_q'],
                                '^' if r['plotted_q']>0 else 'v',
                                color=cell_color(cell), ms=3, alpha=.65)
            bands = np.full((3,len(ns)), np.nan)
            for i,n in enumerate(ns):
                qs=[t[n]['plotted_q'] for t in tracks.values() if n in t]
                if qs:
                    bands[:,i]=lane-scale*np.quantile(qs,[.16,.5,.84])
            ax.fill_between(ns,bands[0],bands[2],color='black',alpha=.045)
            ax.plot(ns,bands[1],color='black',lw=1.1)
            for fraction, text in [(0.001,'0.1%'),(.01,'1%'),(.1,'10%')]:
                q=math.log10(1+fraction/args.r0)
                if q<=args.clip:
                    for sign in (-1,1):
                        y=lane-sign*scale*q
                        ax.plot([ns[0]-.21,ns[0]-.13],[y,y],color='0.3',lw=.6)
                        ax.text(ns[0]-.24,y,('+' if sign>0 else '−')+text,
                                ha='right',va='center',fontsize=5.5)
        ax.set_title(title, fontsize=13, loc='left')
        ax.set_xticks(ns,labels,rotation=25,ha='right',fontsize=8)
        ax.tick_params(labelbottom=True,labelleft=True)
        ax.set_yticks(range(1,len(datasets)+1),[d.upper() for d in datasets])
        ax.set_ylim(len(datasets)+.55,.45)
        ax.set_xlim(ns[0]-.8,ns[-1]+.2)
        ax.grid(axis='x',alpha=.15)
    title = 'Changes between consecutive fits' if mode=='step' else 'Differences from the same cell’s legacy R5 fit'
    fig.suptitle(f'LFHCal fit parameters — {model}\n{title}',fontsize=17,y=.985)
    fig.text(.5,.016,f'Signed-log fractional change; r₀={args.r0:g}. Same cell colors throughout. '
             f'Black: median / central 68%.\nOnly newly saved fits; missing fits and zero denominators are gaps. '
             f'Triangles: clipped values ({clipped_total} points, |q|>{args.clip:g}).',
             ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.07,1,.93))
    save(fig,Path(str(args.out)+f'-{mode}-{model}'),args.pdf)


def absolute(data, ds, last, args):
    fig,axs=plt.subplots(4,2,figsize=(15,13),sharex=True,sharey='row')
    for i,(p,title) in enumerate(PARAMETERS):
        for j,model in enumerate(MODELS):
            ax=axs[i,j]
            for cell in sorted({c for m,c,n in data[ds] if m==model}):
                ys=[value(data[ds],model,cell,n,p) for n in range(last+1)]
                ax.plot(range(last+1),[y if y is not None else np.nan for y in ys],
                        color=cell_color(cell),alpha=args.alpha,lw=.65,marker='.',ms=2)
            ax.set_yscale('symlog',linthresh=.1)
            ax.grid(alpha=.15)
            ax.set_ylabel(f'{title} (ADC; symlog)')
            if i==0:
                ax.set_title(model.capitalize(),fontsize=14)
            ax.set_xticks(range(last+1),[label(n) for n in range(last+1)])
    fig.suptitle(f'{ds.upper()} — absolute fit parameters',fontsize=18)
    fig.text(.5,.012,'Same cell colors and shared row scales for both methods. '
             'Linear within ±0.1 ADC, logarithmic outside. Only newly saved fits; missing fits are gaps.',
             ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.035,1,.96))
    save(fig,Path(str(args.out)+f'-absolute-{ds}'),args.pdf)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,action='append',required=True)
    ap.add_argument('--replace-report',type=Path,action='append',default=[])
    ap.add_argument('--datasets',nargs='+',default=['b1','b2','e1','e2','e3'])
    ap.add_argument('--absolute-dataset',default='b2')
    ap.add_argument('--out',type=Path,default=Path('lfhcal-fit-parameters'))
    ap.add_argument('--max-stage',type=int,default=None)
    ap.add_argument('--r0',type=float,default=1e-4)
    ap.add_argument('--clip',type=float,default=4)
    ap.add_argument('--alpha',type=float,default=.16)
    ap.add_argument('--pdf',action='store_true')
    args=ap.parse_args()
    if not (args.r0>0 and args.clip>0 and 0<args.alpha<=1):
        ap.error('r0 and clip must be positive; alpha must be in (0,1]')
    data,sources=load(args.root,args.replace_report)
    datasets=[d.lower() for d in args.datasets]
    for ds in datasets+[args.absolute_dataset.lower()]:
        if ds not in data:
            ap.error(f'Missing dataset: {ds}')
    last=args.max_stage if args.max_stage is not None else max(n for d in datasets for _,_,n in data[d])
    if last<1:
        ap.error('Need at least one refinement')
    rows=measures(data,datasets,last,args.r0,args.clip)
    if not rows:
        ap.error('No newly saved finite fit parameters found')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    write_csv(Path(str(args.out)+'-values.csv'),rows)
    Path(str(args.out)+'-sources.json').write_text(json.dumps(dict(sources=sources,
        datasets=datasets,max_stage=last,r0=args.r0,clip=args.clip,
        fixed_reference='legacy R5, newly saved fit only',
        gap_policy='Both endpoint fits required; zero denominator omitted'),indent=2)+'\n')
    for mode in ('step','legacy-r5'):
        for model in MODELS:
            nord(rows,datasets,model,mode,last,args)
    absolute(data,args.absolute_dataset.lower(),last,args)


if __name__=='__main__':
    main()
