#!/usr/bin/env python3
"""Summarize every trial without choosing a preferred boundary by fit result."""
import csv,json,zipfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
base=Path(__file__).resolve().parent;out=base/'boundary-output';out.mkdir(exist_ok=True)
rows=[json.loads(l) for d in ('boundary-b1','boundary-other') for l in (base/d/'boundary.jsonl').read_text().splitlines()]
assert len(rows)==360 and len({r['key'] for r in rows})==360
prior=[json.loads(l) for l in (base/'production-candidate/production_candidate.jsonl').read_text().splitlines()]
old=[json.loads(l) for d in ('scan-b1','scan-b2','scan-e') for l in (base/d/'scan.jsonl').read_text().splitlines()]
summary=[]
for ds,cell,src in sorted({(r['dataset'],r['cell_id'],r['histogram_source']) for r in rows}):
 rs=[r for r in rows if (r['dataset'],r['cell_id'],r['histogram_source'])==(ds,cell,src)]
 central=next(r for r in rs if r['axis']=='lower' and r['offset']==0);h=central['smooth_peak'][0]
 former=next(r for r in prior if (r['dataset'],r['cell_id'],r['histogram_source'])==(ds,cell,src));assert abs(h/former['smooth_peak'][0]-1)<1e-9
 baseline=next(r for r in old if (r['dataset'],r['cell_id'],r['histogram_source'])==(ds,cell,src) and r['variant']=='baseline')
 def pct(r):return 100*(r['smooth_peak'][0]/h-1)
 near=[r for r in rs if r['axis']=='lower' and abs(r['offset'])<=1]
 stress=[r for r in rs if r['axis']=='lower'];upper=[r for r in rs if r['axis']=='upper']
 summary.append(dict(dataset=ds,cell=cell,source=src,usable_valley=central['range_rule']['usable'],H=h,lower=central['lower'],radius=central['radius'],shift_from_old_pct=100*(h/baseline['smooth_peak'][0]-1),near_min_pct=min(map(pct,near)),near_max_pct=max(map(pct,near)),near_span_pct=max(map(pct,near))-min(map(pct,near)),stress_max_abs_pct=max(abs(pct(r)) for r in stress),upper_max_abs_pct=max(abs(pct(r)) for r in upper),failed=sum(not r['accepted_by_production_checks'] for r in rs),peak_outside=sum(not r['lower']<r['smooth_peak'][0]<r['upper'] for r in rs)))
(out/'summary.json').write_text(json.dumps(summary,indent=2));(out/'all-trials.json').write_text(json.dumps(rows))
with (out/'summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
fig,axs=plt.subplots(2,4,figsize=(15,7),sharex=True,layout='constrained')
for ax,cell in zip(axs.flat,sorted({r['cell_id'] for r in rows if r['dataset']=='b1'})):
 for src,color in [('legacy','#b85c16'),('adaptive','#1565a6')]:
  rs=sorted([r for r in rows if r['dataset']=='b1' and r['cell_id']==cell and r['histogram_source']==src and r['axis']=='lower'],key=lambda r:r['offset'])
  center=next(r for r in rs if r['offset']==0)['smooth_peak'][0]
  ax.plot([r['offset'] for r in rs],[100*(r['smooth_peak'][0]/center-1) for r in rs],'o-',color=color,label=src+' selected')
  for r in rs:
   if not r['accepted_by_production_checks']:ax.plot(r['offset'],100*(r['smooth_peak'][0]/center-1),'rx',ms=10)
 s=next(s for s in summary if s['dataset']=='b1' and s['cell']==cell and s['source']=='adaptive')
 ax.set_title(f'B1 cell {cell} | original → candidate {s["shift_from_old_pct"]:+.2f}% ',fontsize=10);ax.axhline(0,color='gray',lw=.6);ax.axvspan(-1,1,color='gray',alpha=.1);ax.grid(alpha=.2);ax.set_ylabel('H change from candidate (%)');ax.set_xlabel('Lower-edge offset / radius')
axs.flat[0].legend(fontsize=8);fig.suptitle('B1 calibration sensitivity near the proposed lower edge\nRadius = max(2 bins, 5% observed peak); gray band is the primary neighborhood',fontsize=13)
fig.savefig(out/'b1-boundary-stability.png',dpi=150);plt.close(fig)
print(json.dumps(summary,indent=2))
