#!/usr/bin/env python3
"""Independent lower/upper boundary perturbations; no best-fit selection."""
import argparse,copy,json
from pathlib import Path
from run_fit_range_study import compile_models,setup_case,smoothed_valley,fit_one,sha

def main():
 p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--datasets',nargs='+');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 import ROOT
 ROOT.gROOT.SetBatch(True)
 m=json.loads((a.bundle/'manifest.json').read_text());assert sha(a.bundle/'histograms.root')==m['histograms_root_sha256'];sources=compile_models(ROOT,a.bundle,m)
 meta=dict(root_version=ROOT.gROOT.GetVersion(),histogram_sha256=m['histograms_root_sha256'],sources=sources,rule='Lower radius=max(2 bin widths,5% observed peak); upper radius=10% original upper edge. Independent perturbations; production budget, starts and area limits recomputed. No selection by fit result.')
 (a.out/'environment.json').write_text(json.dumps(meta,indent=2))
 path=a.out/'boundary.jsonl';done={r['key'] for r in map(json.loads,path.read_text().splitlines())} if path.exists() else set()
 f=ROOT.TFile.Open(str(a.bundle/'histograms.root'))
 for c in m['cases']:
  if a.datasets and c['dataset'] not in a.datasets:continue
  h=f.Get(c['root_path']);s=setup_case(ROOT,a.bundle,m,c,h);rule=smoothed_valley(h,s,2.);lo=rule.get('lower',s['xmin']);radius=max(2*h.GetBinWidth(1),.05*rule.get('observed_peak',s['avg']))
  trials=[('lower',v, max(h.GetXaxis().GetXmin(),lo+v*radius),s['xmax']) for v in (-2,-1,-.5,0,.5,1,2)]
  trials += [('upper',v,lo,s['xmax']*(1+.1*v)) for v in (-1,1)]
  for axis,v,l,u in trials:
   key=f'{c["dataset"]}:{c["cell_id"]}:{c["model"]}:{axis}:{v}'
   if key in done:continue
   t=copy.deepcopy(s);t['xmax']=u;integral=int(h.Integral(h.FindBin(l),h.FindBin(u)));t['starts'][2]=float(integral);t['limits'][2]=[1.,5.*integral]
   r=fit_one(ROOT,h,t,'adaptive',l,key,budget=1000)
   r.update(key=key,dataset=c['dataset'],cell_id=c['cell_id'],histogram_source=c['model'],axis=axis,offset=v,radius=radius,range_rule=rule,first_bin=h.FindBin(l),last_bin=h.FindBin(u))
   with path.open('a') as out:out.write(json.dumps(r,allow_nan=False)+'\n')
   print(key,r['status'],r.get('smooth_peak',[None])[0],flush=True)
if __name__=='__main__':main()
