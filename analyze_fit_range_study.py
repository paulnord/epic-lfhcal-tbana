#!/usr/bin/env python3
"""Make scientific overlays and a machine-readable audit of the frozen study."""
import argparse,csv,json,math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from run_fit_range_study import compile_models

def read(path):return list(map(json.loads,path.read_text().splitlines()))
def number(value):
 try:return float(value)
 except (ValueError,TypeError):return None
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--bundle',type=Path,required=True);ap.add_argument('--study',type=Path,required=True)
 args=ap.parse_args();p=args.bundle.resolve();study=args.study.resolve();out=study/'output';out.mkdir(exist_ok=True);(out/'plots').mkdir(exist_ok=True)
 m=json.loads((p/'manifest.json').read_text());baseline=read(study/'seeded-baseline/baseline.jsonl')
 scan=sum([read(study/name/'scan.jsonl') for name in ('scan-b1','scan-b2','scan-e')],[]);candidate=read(study/'candidate/candidate.jsonl')
 assert (len(baseline),len(scan),len(candidate))==(80,320,120)
 allrows=baseline+scan+candidate;assert len({r['key'] for r in allrows})==520
 import ROOT
 ROOT.gROOT.SetBatch(True);compile_models(ROOT,p,m)
 by={r['key']:r for r in allrows};cases={(c['dataset'],c['cell_id'],c['model']):c for c in m['cases']}
 metrics=[]
 for r in allrows:
  c=cases[(r['dataset'],r['cell_id'],r['histogram_source'])];prefix=f"{r['dataset']}:{r['cell_id']}:{r['histogram_source']}"
  info=by[prefix+':valley_2.0']['range_rule'];peak=info.get('observed_peak')
  edges=np.array(c['histogram']['edges']);xs=(edges[1:]+edges[:-1])/2;ys=np.array(c['histogram']['contents'][1:-1])
  r['peak_inside_fit']=r['lower']<r['smooth_peak'][0]<r['upper']
  if peak:
   mask=(xs>=.7*peak)&(xs<=1.6*peak);xx=xs[mask];n=ys[mask]
   mu=np.array(ROOT.RangeStudy.evaluate(r['evaluator']=='adaptive',r['pars'],xx.tolist()));mu=np.maximum(mu,1e-300)
   terms=mu-n;pos=n>0;terms[pos]+=n[pos]*np.log(n[pos]/mu[pos])
   r['common_core']={'lo':.7*peak,'hi':1.6*peak,'bins':int(sum(mask)),'deviance':float(2*sum(terms)),'deviance_per_bin':float(2*np.mean(terms))}
  flat={k:r[k] for k in ('key','dataset','cell_id','histogram_source','variant','evaluator','lower','upper','budget','status','accepted_by_production_checks','peak_inside_fit','calls')}
  flat.update(H=r['smooth_peak'][0],FWHM=r['smooth_peak'][1],landau_width=r['pars'][0],MPV=r['pars'][1],area=r['pars'][2],gaussian_sigma=r['pars'][3],limits_hit=','.join(map(str,r['limits_hit'])),core_deviance_per_bin=r.get('common_core',{}).get('deviance_per_bin',''))
  metrics.append(flat)
 with (out/'all-fit-results.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=metrics[0]);w.writeheader();w.writerows(metrics)
 (out/'all-fit-results.json').write_text(json.dumps(allrows,indent=2,allow_nan=False)+'\n')
 summaries=[]
 for c in m['cases']:
  ds,cell,model=c['dataset'],c['cell_id'],c['model'];k=f'{ds}:{cell}:{model}'
  b=by[k+':baseline'];v=by[k+':valley_2.0'];h=b['smooth_peak'][0];h2=v['smooth_peak'][0]
  variants=[by[k+f':valley_{s:.1f}'] for s in (1.5,2.,3.)]
  row=dict(dataset=ds,cell=cell,source=model,original_saved=c['fit'] is not None,
           original_H=number(c['audit_row']['scale_h']),baseline_H=h,candidate_H=h2,change_percent=100*(h2/h-1),
           old_lower=b['lower'],new_lower=v['lower'],old_sigma=b['pars'][3],new_sigma=v['pars'][3],
           old_accepted=b['accepted_by_production_checks'],new_accepted=v['accepted_by_production_checks'],
           rule=v['range_rule'],core_old=b.get('common_core'),core_new=v.get('common_core'),
           smoothing_H_span_percent=100*(max(q['smooth_peak'][0] for q in variants)-min(q['smooth_peak'][0] for q in variants))/abs(h2),
           all_smoothing_rules_usable=all(q['range_rule']['usable'] for q in variants))
  summaries.append(row)
 (out/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.15,'savefig.facecolor':'white'})
 colors=['#a14620','#006eae']
 pairs=list(dict.fromkeys((c['dataset'],c['cell_id']) for c in m['cases']))
 with PdfPages(out/'lfhcal-range-overlays.pdf') as pdf, PdfPages(out/'lfhcal-range-scans.pdf') as scanpdf:
  for ds,cell in pairs:
   fig,axs=plt.subplots(1,2,figsize=(12,5.1));fig.subplots_adjust(left=.065,right=.98,top=.81,bottom=.19,wspace=.18)
   ymax=0.;xmax=0.
   for ax,source in zip(axs,('legacy','adaptive')):
    c=cases[ds,cell,source];k=f'{ds}:{cell}:{source}';b=by[k+':baseline'];v=by[k+':valley_2.0'];edges=np.array(c['histogram']['edges']);xs=(edges[1:]+edges[:-1])/2;ys=np.array(c['histogram']['contents'][1:-1]);xmax=max(xmax,b['upper']*1.05)
    ax.stairs(ys,edges,color='#555555',linewidth=.65,alpha=.7,label='Original counts')
    for r,color,label in [(b,colors[0],'Original window'),(v,colors[1],'Valley window')]:
     xx=np.linspace(r['lower'],r['upper'],1501);yy=ROOT.RangeStudy.evaluate(True,r['pars'],xx.tolist())
     accepted=r['accepted_by_production_checks'];suffix='' if accepted else ' [rejected]'
     ax.plot(xx,yy,color=color,lw=1.7,ls='-' if accepted else '--',label=f"{label}: H={r['smooth_peak'][0]:.2f}{suffix}")
     ax.axvline(r['lower'],color=color,lw=.8,ls=':',alpha=.8)
    ax.set(title=f'{source.capitalize()}-selected histogram',xlabel='Pedestal-subtracted ADC',ylabel='Count per original bin')
    ymax=max(ymax,max(ys[(xs>=3*b['setup']['ped'])&(xs<b['upper'])])*1.12)
    ax.legend(loc='upper right',framealpha=.9,fontsize=8.2)
   for ax in axs:ax.set(xlim=(0,xmax),ylim=(0,ymax))
   fig.suptitle(f'{ds.upper()} cell {cell} | Same adaptive model, different fit window',fontsize=14,y=.96)
   v=by[f'{ds}:{cell}:adaptive:valley_2.0'];b=by[f'{ds}:{cell}:adaptive:baseline'];rule=v['range_rule']
   text=f"Adaptive-selected input: lower edge {b['lower']:.1f} → {v['lower']:.1f} ADC; Gaussian σ {b['pars'][3]:.2f} → {v['pars'][3]:.2f}."
   if not rule['usable']:text+='\nNo range change proposed: '+rule['reason']+'.'
   else:text+='\nOnly range-finding uses smoothing; fit uses the original bins. Dotted lines mark lower edges.'
   fig.text(.065,.055,text,fontsize=9)
   fig.savefig(out/'plots'/f'{ds}-cell{cell}-overlay.png',dpi=160);pdf.savefig(fig);plt.close(fig)
   # One source population per scan panel; rejected / extrapolated peaks explicit.
   fig,axs=plt.subplots(1,2,figsize=(12,4.8));fig.subplots_adjust(left=.075,right=.98,top=.82,bottom=.2,wspace=.2)
   for ax,source in zip(axs,('legacy','adaptive')):
    k=f'{ds}:{cell}:{source}';rows=[by[k+':baseline']]+[by[k+f':floor_{f:.2f}'] for f in (.3,.45,.6,.75,.9,1.05)];rows=sorted(rows,key=lambda r:r['lower'])
    xx=[r['lower'] for r in rows];hh=[r['smooth_peak'][0] for r in rows]
    ax.plot(xx,hh,lw=.8,c='#aaa')
    for r in rows:
     ok=r['accepted_by_production_checks'] and r['peak_inside_fit'];ax.scatter(r['lower'],r['smooth_peak'][0],marker='o' if ok else 'x',c=colors[1] if ok else '#b53430',s=40,zorder=3)
    v=by[k+':valley_2.0'];ax.scatter(v['lower'],v['smooth_peak'][0],marker='D',c='#168451',s=52,zorder=4)
    ax.plot([min(xx),max(xx)],[min(xx),max(xx)],'--',c='#777',lw=.8)
    ax.set(title=f'{source.capitalize()}-selected histogram',xlabel='Lower fit boundary (ADC)',ylabel='Smooth convolved peak H (ADC)')
   fig.suptitle(f'{ds.upper()} cell {cell} | Lower-bound sensitivity',fontsize=14)
   fig.text(.07,.055,'Blue circle: passes production checks and peak lies inside fitted range. Red ×: fails either check.\nGreen diamond: valley candidate (unchanged baseline when flagged). Dashed diagonal: H = lower boundary.',fontsize=9)
   fig.savefig(out/'plots'/f'{ds}-cell{cell}-scan.png',dpi=150);scanpdf.savefig(fig);plt.close(fig)
   print('Plotted',ds,cell,flush=True)
 # A numerical-artifact example, using one identical histogram for both curves.
 c=cases['e2',1344,'legacy'];r=by['e2:1344:legacy:baseline'];f=c['fit'];pars=[q['value'] for q in f['parameters']]
 fig,ax=plt.subplots(figsize=(10,5));edges=np.array(c['histogram']['edges']);ax.stairs(c['histogram']['contents'][1:-1],edges,color='#555',lw=.8,label='Same original histogram')
 lo,hi=f['xmin'],min(40,f['xmax']);xx=np.linspace(lo,hi,max(3001,int((hi-lo)/(pars[0]/16))))
 ax.plot(xx,ROOT.RangeStudy.evaluate(False,pars,xx.tolist()),c=colors[0],lw=1,label='Saved legacy evaluator and parameters')
 xx=np.linspace(r['lower'],40,1501);ax.plot(xx,ROOT.RangeStudy.evaluate(True,r['pars'],xx.tolist()),c=colors[1],lw=2,label='Adaptive refit, same original window')
 ax.set(xlim=(0,40),ylim=(0,3500),xlabel='Pedestal-subtracted ADC',ylabel='Count per original bin',title='E2 cell 1344 | Numerical integration is a separate issue');ax.legend(fontsize=9);fig.tight_layout();fig.savefig(out/'plots/e2-cell1344-evaluator.png',dpi=180);plt.close(fig)
 print('Analysis complete:',out,flush=True)
if __name__=='__main__':main()
