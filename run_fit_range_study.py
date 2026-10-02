#!/usr/bin/env python3
"""Frozen-histogram ROOT study. Never changes the input bundle or calibrations.

baseline: production limits/budget, raw and finite empty-bin errors, both methods.
scan: adaptive evaluator on BOTH selected-histogram populations, fixed starts and
      limits, uniform 10000-call/1000-iteration budget, lower range boundary only.
One JSONL record per completed fit; reruns resume by a unique fit key.
"""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import re
import time


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_models(ROOT, bundle, manifest):
    parents=[bundle/'campaigns'/name for name in manifest['campaigns']]
    hashes=[]
    for parent in parents:
        expected=json.loads((parent/'source-hashes.json').read_text())
        for model,rel in [('legacy','NewStructure/TileSpectra.cc'),
                          ('adaptive','NewStructure/TileSpectra.cc'),
                          ('adaptive','NewStructure/AdaptiveLangau.h')]:
            path=parent/'sources'/model/rel
            assert sha(path)==expected[model][rel], str(path)
            hashes.append((model,rel,sha(path)))
    assert hashes[:3]==hashes[3:6], 'Campaign evaluators differ'
    parent=parents[0]
    src=(parent/'sources/legacy/NewStructure/TileSpectra.cc').read_text()
    start=src.index('double TileSpectra::langaufun(double *x, double *par)')
    end=src.index('int TileSpectra::langaupro(',start)
    legacy=src[start:end].strip().replace('TileSpectra::langaufun','legacy',1)
    assert legacy.endswith('}')
    src=(parent/'sources/adaptive/NewStructure/TileSpectra.cc').read_text()
    expr=re.search(r'return lfhcal::adaptive_langau::Convolution\([\s\S]*?\}\)\(x\[0\]\);',src).group()
    header=parent/'sources/adaptive/NewStructure/AdaptiveLangau.h'
    ROOT.gSystem.Load('libMinuit')
    decl='#include <TF1.h>\n#include <TMath.h>\n#include <TMinuit.h>\n#include <vector>\n#include '+json.dumps(str(header))+'\n'
    decl+='namespace RangeStudy {\n'+legacy+'\ndouble adaptive(double* x,double* p){'+expr+'}\n'
    decl+='''
void resetSeed(int seed) {
 static TMinuit* helper=new TMinuit(4);
 double flag=3.;helper->mnrn15(flag,seed);
}
TF1* make(bool useAdaptive, const char* name,double lo,double hi) {
 return new TF1(name,useAdaptive?adaptive:legacy,lo,hi,4);
}
std::vector<double> peak(const std::vector<double>& pars) {
 auto p=pars;
 auto w=lfhcal::adaptive_langau::peakWidth(
 [&](double x){return adaptive(&x,p.data());},p[1],std::max(p[0],p[3]));
 return {w.peak,w.fwhm,w.height,w.left,w.right};
}
std::vector<double> evaluate(bool useAdaptive,const std::vector<double>& pars,
                            const std::vector<double>& xs) {
 auto p=pars;std::vector<double> y;y.reserve(xs.size());
 for(double x:xs)y.push_back(useAdaptive?adaptive(&x,p.data()):legacy(&x,p.data()));
 return y;
}
}
'''
    assert ROOT.gInterpreter.Declare(decl)
    return hashes


def read_calib(path):
    text=path.read_text()
    vov=float(re.search(r'Vov:\s*([\d.]+)',text).group(1))
    rows={}
    for line in text.splitlines():
        fields=line.split()
        if len(fields)==18 and fields[0].isdigit(): rows[int(fields[0])]=list(map(float,fields))
    active=[r[9] for r in rows.values() if r[9]!=-1000 and r[17]>=2]
    return rows,vov,sum(active)/len(active)


def setup_case(ROOT,bundle,manifest,c,h):
    peers=[d for d in manifest['cases'] if d['dataset']==c['dataset'] and d['model']==c['model'] and d['fit']]
    rows,vov,avg_text=read_calib(bundle/'context'/c['dataset']/c['model']/'previous-calibration.txt')
    # Original Setup tree was not packed. SumV2 layer sizes are checked against
    # ALL saved TF1 ranges/limits; this bundle's layers 0..3 sum 5, 4..7 sum 10.
    layer=int(rows[c['cell_id']][1]);layers=5 if layer<4 else 10
    p=peers[0];pl=int(rows[p['cell_id']][1]);avg=p['fit']['xmax']/(3 if pl<4 else 4)/(1.2 if vov>6 else 1)
    assert abs(avg-avg_text)<1e-5, (avg,avg_text)
    saved=c['fit']
    donor=saved or next((d['fit'] for d in manifest['cases'] if d['dataset']==c['dataset'] and d['cell_id']==c['cell_id'] and d['fit']),None)
    ped=donor['parameters'][3]['lower']/(.001 if vov<4 else .01) if donor else rows[c['cell_id']][6]
    assert abs(ped-rows[c['cell_id']][6])<1e-5
    xmin_default=(.3 if layers<6 else .6)*avg;xmax=(3 if layers<6 else 4)*avg*(1.2 if vov>6 else 1)
    # Production helper takes float minX/maxX, so preserve float32 conversion.
    import struct
    high=struct.unpack('f',struct.pack('f',.8*avg))[0]
    bins=range(h.FindBin(0.),h.FindBin(high)+1)
    minimum=min(bins,key=lambda b:h.GetBinContent(b))
    valley=h.GetBinCenter(minimum);xmin=min(xmin_default,valley)
    integral=int(h.Integral(h.FindBin(xmin),h.FindBin(xmax)))
    limits=[[(.01 if vov<4.5 else .1),(150 if vov>6 else 100)],
            [min((.3 if layers<6 else .5)*avg,valley),(2.2 if layers<6 else 3.5)*avg*(1.2 if vov>6 else 1)],
            [1.,5.*integral],
            [ped*(.001 if vov<4 else .01),ped*(30 if layers<6 else 50)*(2 if vov>6 else 1)]]
    if saved:
        assert abs(xmin-saved['xmin'])<1e-6 and abs(xmax-saved['xmax'])<1e-6
        for actual,p in zip(limits,saved['parameters']):
            assert max(abs(actual[0]-p['lower']),abs(actual[1]-p['upper']))<1e-5,(c['root_path'],actual,p)
        limits=[[p['lower'],p['upper']] for p in saved['parameters']]
        xmin,xmax=saved['xmin'],saved['xmax']
    return dict(avg=avg,avg_from_text=avg_text,ped=ped,vov=vov,layers=layers,
                pedestal_precision='saved_TF1_limit' if donor else 'rounded_previous_calibration',previous_cell_H=rows[c['cell_id']][9],xmin=xmin,xmax=xmax,
                nominal_xmin=xmin_default,valley=valley,limits=limits,
                starts=[ped*3,avg,float(integral),ped])


def fit_one(ROOT,h,setup,model,lower,variant,original_errors=False,budget=10000):
    hc=h.Clone('working_hist');hc.SetDirectory(0)
    changed=[]
    for b in range(hc.GetNbinsX()+2):
        err=hc.GetBinError(b)
        if not math.isfinite(err):
            assert hc.GetBinContent(b)==0, 'Unexpected nonfinite error in occupied bin'
            if not original_errors:hc.SetBinError(b,0.);changed.append(b)
    f=ROOT.RangeStudy.make(model=='adaptive','range_fit',lower,setup['xmax'])
    ROOT.SetOwnership(f,True)
    f.SetParameters(array('d',setup['starts']))
    for i,(lo,hi) in enumerate(setup['limits']):f.SetParLimits(i,lo,hi)
    ROOT.Math.MinimizerOptions.SetDefaultMaxFunctionCalls(budget)
    ROOT.Math.MinimizerOptions.SetDefaultMaxIterations(100 if budget==1000 else 1000)
    ROOT.RangeStudy.resetSeed(12345)
    start=time.monotonic()
    r=hc.Fit(f,'QRLMN0S')
    elapsed=time.monotonic()-start
    pars=[f.GetParameter(i) for i in range(4)]
    limits_hit=[i for i,(a,(lo,hi)) in enumerate(zip(pars,setup['limits'])) if min(abs(a-lo),abs(a-hi))<1e-5]
    status=int(r)
    out=dict(variant=variant,evaluator=model,lower=lower,upper=setup['xmax'],budget=budget,
             original_errors=original_errors,changed_error_bins=changed,status=status,
             minimizer=str(r.MinimizerType()),improve_random_seed=12345,
             root_valid=bool(r.IsValid()),function_valid=bool(f.IsValid()),limits_hit=limits_hit,
             accepted_by_production_checks=bool(f.IsValid() and status in (0,4000,70,4070) and not limits_hit),
             pars=pars,errors=[f.GetParError(i) for i in range(4)],covariance=[[r.CovMatrix(i,j) for j in range(4)] for i in range(4)],
             covariance_status=r.CovMatrixStatus(),edm=r.Edm(),calls=r.NCalls(),
             min_fcn=r.MinFcnValue(),chi2=f.GetChisquare(),ndf=f.GetNDF(),fit_points=f.GetNumberFitPoints(),seconds=elapsed)
    # Always compute the smooth continuous convolution's peak. For legacy this
    # is a diagnostic, NOT the production stepping algorithm's reported H.
    try: out['smooth_peak']=list(ROOT.RangeStudy.peak(pars))
    except Exception as exc:out['peak_error']=str(exc)
    ROOT.SetOwnership(hc,True)
    return out


def smoothed_valley(h,setup,sigma):
    """A single explicit range rule; smoothing is NEVER applied to fitted data."""
    import numpy as np
    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import find_peaks
    x=np.array([h.GetBinCenter(b) for b in range(1,h.GetNbinsX()+1)])
    y=np.array([h.GetBinContent(b) for b in range(1,h.GetNbinsX()+1)])
    smooth=gaussian_filter1d(y,sigma)
    band=(x>=max(3*setup['ped'],.5*setup['avg']))&(x<=2.5*setup['avg'])
    peaks,prop=find_peaks(smooth,prominence=.2*max(smooth[band]),distance=4*sigma)
    good=[i for i,j in enumerate(peaks) if band[j]]
    info=dict(smoothing_sigma_bins=sigma,band=[max(3*setup['ped'],.5*setup['avg']),2.5*setup['avg']])
    if not good:return dict(info,usable=False,reason='No prominent peak in expected band')
    peak=peaks[max(good,key=lambda i:prop['prominences'][i])]
    indices=np.where((x>=3*setup['ped'])&(x<=.8*x[peak]))[0]
    if len(indices)<3:return dict(info,usable=False,reason='Insufficient space below peak')
    valley=indices[np.argmin(smooth[indices])]
    info.update(observed_peak=float(x[peak]),valley=float(x[valley]),valley_fraction=float(smooth[valley]/smooth[peak]))
    if valley==indices[0] or valley==indices[-1]:
        return dict(info,usable=False,reason='Minimum at search boundary; no resolved valley')
    if info['valley_fraction']>.5:return dict(info,usable=False,reason='Shallow valley')
    lower=max(setup['xmin'],float(x[valley]))
    if lower>=x[peak]:return dict(info,usable=False,reason='Range excludes observed peak')
    return dict(info,usable=True,lower=lower)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bundle',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--phase',choices=['baseline','adaptive_baseline','scan','candidate','production_candidate'],required=True)
    ap.add_argument('--case',help='Optional dataset:cell:model')
    ap.add_argument('--datasets',nargs='+',help='Optional independent dataset partition')
    args=ap.parse_args();args.bundle=args.bundle.resolve();args.out.mkdir(parents=True,exist_ok=True)
    import ROOT
    ROOT.gROOT.SetBatch(True)
    m=json.loads((args.bundle/'manifest.json').read_text())
    assert sha(args.bundle/'histograms.root')==m['histograms_root_sha256']
    models=compile_models(ROOT,args.bundle,m)
    metadata=dict(root_version=ROOT.gROOT.GetVersion(),original_root_version=m['extraction_root_version'],
                  minimizer=ROOT.Math.MinimizerOptions.DefaultMinimizerType(),
                  algorithm=ROOT.Math.MinimizerOptions.DefaultMinimizerAlgo(),
                  tolerance=ROOT.Math.MinimizerOptions.DefaultTolerance(),
                  histogram_sha256=m['histograms_root_sha256'],sources=models,fit_options='QRLMN0S',
                  improve_random_seed=12345,
                  scan_note='Original starts, parameter limits and upper edge fixed; independently fit each lower edge. No best-of selection.')
    metadata=json.loads(json.dumps(metadata))  # Normalize tuples before resume comparison.
    env=args.out/'environment.json'
    if env.exists() and json.loads(env.read_text())!=metadata:
        raise ValueError('Existing output has different provenance/settings; use a new --out directory')
    env.write_text(json.dumps(metadata,indent=2)+'\n')
    results=args.out/(args.phase+'.jsonl')
    done={r['key'] for r in map(json.loads,results.read_text().splitlines())} if results.exists() else set()
    file=ROOT.TFile.Open(str(args.bundle/'histograms.root'),'READ')
    for c in m['cases']:
        if args.datasets and c['dataset'] not in args.datasets:continue
        case=f'{c["dataset"]}:{c["cell_id"]}:{c["model"]}'
        if args.case and args.case!=case:continue
        h=file.Get(c['root_path']);setup=setup_case(ROOT,args.bundle,m,c,h)
        if args.phase=='baseline':
            variants=[('original',setup['xmin'],True,1000,c['model']),('finite_errors',setup['xmin'],False,1000,c['model'])]
        elif args.phase=='adaptive_baseline':
            variants=[('adaptive_original_window',setup['xmin'],False,1000,'adaptive')]
        elif args.phase=='scan':
            variants=[('baseline',setup['xmin'],False,10000,'adaptive'),
                      ('nominal_floor',setup['nominal_xmin'],False,10000,'adaptive')]
            variants += [(f'floor_{frac:.2f}',max(setup['xmin'],frac*setup['avg']),False,10000,'adaptive') for frac in (.3,.45,.6,.75,.9,1.05)]
        else:
            variants=[]
            for sigma in ((2.,) if args.phase=='production_candidate' else (1.5,2.,3.)):
                info=smoothed_valley(h,setup,sigma)
                lower=info.get('lower',setup['xmin'])
                if args.phase=='production_candidate':
                    # Prospective range-only source edit also changes the area
                    # seed/limit, which production calculates from the range.
                    integral=int(h.Integral(h.FindBin(lower),h.FindBin(setup['xmax'])))
                    setup['starts'][2]=float(integral);setup['limits'][2]=[1.,5.*integral]
                    variants.append(('valley_production',lower,False,1000,'adaptive'))
                else:variants.append((f'valley_{sigma:.1f}',lower,False,10000,'adaptive'))
        for variant,lower,raw,budget,model in variants:
            key=case+':'+variant
            if key in done:continue
            result=fit_one(ROOT,h,setup,model,lower,variant,raw,budget)
            if args.phase=='candidate':result['range_rule']=smoothed_valley(h,setup,float(variant.split('_')[1]))
            if args.phase=='production_candidate':result['range_rule']=smoothed_valley(h,setup,2.)
            result.update(key=key,dataset=c['dataset'],cell_id=c['cell_id'],histogram_source=c['model'],setup=setup)
            with results.open('a') as out:out.write(json.dumps(result,allow_nan=False)+'\n')
            print(key,'status',result['status'],'H',round(result.get('smooth_peak',[float('nan')])[0],4),
                  'calls',result['calls'],'seconds',round(result['seconds'],2),flush=True)
    file.Close()


if __name__=='__main__':main()
