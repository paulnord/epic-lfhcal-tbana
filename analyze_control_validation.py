#!/usr/bin/env python3
"""Report frozen-rule held-out tests; keep rejected fits visible and flagged."""
import argparse,csv,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from run_fit_range_study import compile_models
p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--results',type=Path,required=True);a=p.parse_args();out=a.results/'output';out.mkdir(exist_ok=True)
m=json.loads((a.bundle/'manifest.json').read_text())
def read(phase):return [json.loads(l) for ds in ('b1','b2','e1','e2') for l in (a.results/f'{phase}-{ds}'/(phase+'.jsonl')).read_text().splitlines()]
baselines=read('baseline');old=read('adaptive_baseline');new=read('production_candidate');scan=read('boundary')
assert [len(x) for x in (baselines,old,new,scan)]==[128,64,64,576]
assert len({r['key'] for r in scan})==576
assert len({r['key'] for r in baselines})==128
def key(r):return (r['dataset'],r['cell_id'],r.get('histogram_source',r.get('model')))
old={key(r):r for r in old};new={key(r):r for r in new};orig={key(r):r for r in baselines if r['variant']=='original'}
import ROOT
ROOT.gROOT.SetBatch(True);compile_models(ROOT,a.bundle,m)
summary=[];checks=[]
for c in m['cases']:
 k=key(c);o,n=old[k],new[k];rs=[r for r in scan if key(r)==k];H=n['smooth_peak'][0];bH=o['smooth_peak'][0]
 center=next(r for r in rs if r['axis']=='lower' and r['offset']==0);repro=100*(center['smooth_peak'][0]/H-1)
 def pct(r):return 100*(r['smooth_peak'][0]/H-1)
 near=[r for r in rs if r['axis']=='lower' and abs(r['offset'])<=1];wide=[r for r in rs if r['axis']=='lower'];upper=[r for r in rs if r['axis']=='upper']
 saved=c['fit'];diff=max(abs(v-p['value'])/max(1,abs(p['value'])) for v,p in zip(orig[k]['pars'],saved['parameters'])) if saved else None
 checks.append(dict(dataset=k[0],cell=k[1],source=k[2],saved_parameter_max_scaled_difference=diff,baseline_status=orig[k]['status'],baseline_limits_hit=orig[k]['limits_hit'],pedestal_precision=orig[k]['setup'].get('pedestal_precision','saved_TF1_limit'),central_reproduction_pct=repro))
 edges=np.array(c['histogram']['edges']);xx=(edges[1:]+edges[:-1])/2;yy=np.array(c['histogram']['contents'][1:-1],dtype=float);peak=n['range_rule'].get('observed_peak');core=[]
 for fit in (o,n):
  if peak:
   mask=(xx>=.7*peak)&(xx<=1.6*peak);counts=yy[mask];mu=np.maximum(np.array(ROOT.RangeStudy.evaluate(True,fit['pars'],xx[mask].tolist())),1e-300);terms=mu-counts;pos=counts>0;terms[pos]+=counts[pos]*np.log(counts[pos]/mu[pos]);core.append(float(2*np.mean(terms)))
  else:core.append(None)
 summary.append(dict(core_old_deviance_per_bin=core[0],core_new_deviance_per_bin=core[1],old_gaussian_sigma=o['pars'][3],new_gaussian_sigma=n['pars'][3],dataset=k[0],cell=k[1],source=k[2],saved_fit=bool(saved),usable_valley=n['range_rule']['usable'],window_changed=n['lower']>o['lower']+1e-8,fit_points_changed=n['fit_points']!=o['fit_points'],old_lower=o['lower'],new_lower=n['lower'],original_H=bH,candidate_H=H,change_pct=100*(H/bH-1),old_accepted=o['accepted_by_production_checks'],candidate_accepted=n['accepted_by_production_checks'],near_min_pct=min(map(pct,near)),near_max_pct=max(map(pct,near)),near_max_abs_pct=max(abs(pct(r)) for r in near),stress_max_abs_pct=max(abs(pct(r)) for r in wide),upper_max_abs_pct=max(abs(pct(r)) for r in upper),near_failed=sum(not r['accepted_by_production_checks'] for r in near),scan_failed=sum(not r['accepted_by_production_checks'] for r in rs),peak_outside=sum(not r['lower']<r['smooth_peak'][0]<r['upper'] for r in rs),radius=center['radius'],central_reproduction_pct=repro))
(out/'summary.json').write_text(json.dumps(summary,indent=2));(out/'baseline-checks.json').write_text(json.dumps(checks,indent=2))
with (out/'control-summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
# Avoid silently merging evaluator changes with range changes. Every overlay
# uses the same adaptive model on the same source histogram.
for ds in ('b1','b2','e1','e2'):
 with PdfPages(out/f'{ds}-control-fits.pdf') as pdf:
  for cell in m['selection'][ds]:
   fig,axs=plt.subplots(2,2,figsize=(11,8),layout='constrained')
   for col,src in enumerate(('legacy','adaptive')):
    k=(ds,cell,src);c=next(c for c in m['cases'] if key(c)==k);o,n=old[k],new[k];s=next(s for s in summary if (s['dataset'],s['cell'],s['source'])==k)
    edges=np.array(c['histogram']['edges']);x=(edges[:-1]+edges[1:])/2;y=np.array(c['histogram']['contents'][1:-1],dtype=float)
    peak=n['range_rule'].get('observed_peak',n['smooth_peak'][0]);xmax=max(1.7*peak,1.6*n['smooth_peak'][0]);xs=np.linspace(0,xmax,1200);ax=axs[0,col]
    ax.stairs(y,edges,color='.45',lw=.7,label='Original bins')
    for r,color,label in ((o,'#bf6419','Original window'),(n,'#176aa5','Valley rule')):
     yy=np.array(ROOT.RangeStudy.evaluate(True,r['pars'],xs.tolist()));inside=(xs>=r['lower'])&(xs<=r['upper']);accepted=r['accepted_by_production_checks'];ax.plot(xs,np.where(inside,yy,np.nan),color=color,lw=1.5,ls='-' if accepted else '--',label=label+(' (rejected)' if not accepted else ''));ax.plot(xs,np.where(~inside,yy,np.nan),color=color,lw=.8,ls=':');ax.axvline(r['lower'],color=color,lw=.8,ls=':')
    region=(x>=max(0,.5*peak))&(x<=xmax);ax.set_ylim(0,1.3*max(y[region]));ax.set_xlim(0,xmax);ax.set_title(f'{src.capitalize()}-selected spectrum | H shift {s["change_pct"]:+.2f}%');ax.set_xlabel('ADC');ax.set_ylabel('Entries / original bin');ax.legend(fontsize=8);ax.grid(alpha=.15)
    rs=sorted([r for r in scan if key(r)==k and r['axis']=='lower'],key=lambda r:r['offset']);ax=axs[1,col];h=n['smooth_peak'][0]
    ax.plot([r['offset'] for r in rs],[100*(r['smooth_peak'][0]/h-1) for r in rs],'o-',color='#176aa5')
    for r in rs:
     if not r['accepted_by_production_checks'] or not r['lower']<r['smooth_peak'][0]<r['upper']:ax.plot(r['offset'],100*(r['smooth_peak'][0]/h-1),'rx',ms=10)
    ax.axhline(0,color='.4',lw=.7);ax.axvspan(-1,1,color='.5',alpha=.12);ax.grid(alpha=.2);ax.set_xlabel(f'Lower-edge offset / radius ({s["radius"]:.2f} ADC)');ax.set_ylabel('H change from candidate (%)');ax.set_title(f'Upper-edge +/-10%: max |H change| {s["upper_max_abs_pct"]:.2f}%',fontsize=10)
   title=f'{ds.upper()} cell {cell}: unchanged adaptive evaluator, original bins';flags=[]
   if any(not new[(ds,cell,src)]['range_rule']['usable'] for src in ('legacy','adaptive')):flags.append('No usable valley in at least one spectrum')
   if any(not c['fit'] for c in m['cases'] if c['dataset']==ds and c['cell_id']==cell):flags.append('Original saved fit absent; baseline is a failed-fit diagnostic')
   fig.suptitle(title+'\n'+(' | '.join(flags) if flags else 'Dotted curves: extrapolation; shaded scan: primary neighborhood; red X: rejected or peak outside window'),fontsize=11)
   pdf.savefig(fig);fig.savefig(out/f'{ds}-cell{cell}.png',dpi=110);plt.close(fig)
# One point per adaptive-selected case; matched B2 includes original failures.
fig,axs=plt.subplots(1,2,figsize=(11,5),layout='constrained')
for i,ds in enumerate(('b1','e1','e2')):
 ss=[s for s in summary if s['dataset']==ds and s['source']=='adaptive'];jitter=np.linspace(-.18,.18,len(ss))
 for j,s in enumerate(ss):
  label=ds.upper() if j==0 else None
  for ax,field in zip(axs,('change_pct','near_max_abs_pct')):ax.scatter(i+jitter[j],s[field],marker='o' if s['saved_fit'] and s['candidate_accepted'] else 'x',c=['#176aa5','#bf6419','#21834b','#964fa1'][i],s=35)
for ax,title in zip(axs,('Original window to valley rule','Nearby lower-boundary sensitivity')):
 ax.set_xticks(range(3),['B1','E1','E2']);ax.grid(axis='y',alpha=.2);ax.set_title(title);ax.axhline(0,color='.4',lw=.7)
axs[0].set_ylabel('H change (%)');axs[1].set_ylabel('Maximum absolute H change from candidate (%)');fig.suptitle('24 new agreement-selected controls: adaptive-selected spectra\nB2 counterparts are in the separate atlas; this is not a random detector sample',fontsize=11)
fig.savefig(out/'new-controls-overview.png',dpi=150);plt.close(fig)
print(json.dumps(summary,indent=2))
