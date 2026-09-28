#!/usr/bin/env python3
"""Frozen-histogram Langau benchmark. Never rewrites calibration inputs."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import socket
import statistics
import struct
import subprocess
import sys
import time

SETS = ('b1','b2','c1','c2','c3','d1','d2','e1','e2','e3','f1','f2','g1','g2')
SMOKE = {'e1': (896,903), 'b2': (131,), 'e3': (2759,)}
TARGETS = {'b1': (1024,1094), 'b2': (67,131,454,515,518),
           'c2': (391,839,1479,2118), 'c3': (1415,1859,2951),
           'd1': (391,709,1095), 'e1': (896,903,1153,1223),
           'e2': (1153,1410,2048), 'e3': (386,1153,1795,2048,2759),
           'f1': (1024,), 'f2': (1024,), 'g1': (1024,), 'g2': (1024,)}
PAR_NAMES = ('landau_width','mpv','area','gaussian_sigma')
# Last case doubles the FULL domain and nearly preserves dx by doubling N.
METHODS = (('legacy100','legacy100',0,1.), ('adaptive5','adaptive5',0,1.),
           ('fft10000','fft',10000,1.), ('fft32768','fft',32768,1.),
           ('fft65536','fft',65536,1.), ('fft131072_wide','fft',131072,2.))
FIT_OPTIONS = 'QRLMNS0'  # production QRLMN0 plus S to retain TFitResult
BASE_COMMIT = '3a643646eb301c7112449e8f6d6ab31f12c72943'


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)):
        return [clean(v) for v in value]
    return value


def write_json(path, data):
    path.write_text(json.dumps(clean(data), indent=2, allow_nan=False)+'\n')


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            row = clean(row)
            writer.writerow({k: '?' if row.get(k) is None else row[k] for k in fields})


def read_calib(path):
    text = path.read_text()
    found = re.search(r'Vov:\s*([-+\d.eE]+)', text)
    if not found:
        raise ValueError(f'No Vov in {path}')
    rows = {}
    for line in text.splitlines():
        p = line.split()
        if len(p) != 18 or not p[0].isdigit():
            continue
        cell = int(p[0])
        if cell in rows:
            raise ValueError(f'Duplicate cell {cell} in {path}')
        rows[cell] = {'ped':float(p[6]), 'scale':float(p[9]), 'bc':int(p[17])}
    bc_header = re.search(r'BC calib set:\s*(\d+)', text)
    bc_enabled = bool(int(bc_header.group(1))) if bc_header else True
    vals = [r['scale'] for r in rows.values()
            if r['scale'] != -1000 and (not bc_enabled or r['bc']>=2)]
    if not vals:
        raise ValueError(f'No valid calibration scales in {path}')
    return float(found.group(1)), statistics.mean(vals), rows


def read_segments(path):
    segments = {}
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) == 11 and p[0].isdigit():
            cell = (int(p[7])<<9)+(int(p[5])<<8)+(int(p[6])<<6)+int(p[2])
            if cell in segments:
                raise ValueError(f'Duplicate mapping cell {cell}')
            segments[cell] = int(p[10])
    if not segments:
        raise ValueError(f'No segmentation in {path}')
    return segments


def original_setup(h, ped, avg, vov, layers):
    """Snapshot of original HGCROC improved/native-bin range and seed rules.

    Matches TileSpectra at BASE_COMMIT, not the later sigma-floor experiments.
    This reproduces only the fit SETUP, not the calibration/selection pipeline.
    """
    if not (ped > 0 and avg > 0 and math.isfinite(vov)):
        raise ValueError('Invalid pedestal, global scale, or Vov')
    low_factor, high_factor = ((.6,3.) if layers==1 else
                              (.3,3.) if layers<6 else (.6,4.))
    # GetMinimumInRangeSpectra takes float (not double) endpoints in production.
    end = struct.unpack('f', struct.pack('f', .8*avg))[0]
    bins = range(h.FindBin(0.), h.FindBin(end)+1)
    minimum = min(bins, key=lambda b: (h.GetBinContent(b), b))
    valley = h.GetBinCenter(minimum)
    lo = min(low_factor*avg, valley)
    hi = high_factor*avg*(1.2 if vov > 6 else 1.)
    area = int(h.Integral(h.FindBin(lo), h.FindBin(hi)))
    if area < 1:
        raise ValueError('No counts in candidate fit window')
    mp_lo,mp_hi = ((.5,1.7) if layers==1 else (.3,2.2) if layers<6 else (.5,3.5))
    lower = [.01 if vov < 4.5 else .1, min(mp_lo*avg,valley), 1.,
             ped*(.001 if vov < 4. else .01)]
    upper = [150. if vov > 6 else 100., mp_hi*avg*(1.2 if vov > 6 else 1.),
             5.*area, ped*(50. if layers>5 else 30.)*(2. if vov>6 else 1.)]
    seed = [3.*ped, avg, float(area), ped]
    if not all(a < v < b for a,v,b in zip(lower,seed,upper)):
        raise ValueError('Original seed not strictly inside bounds; not silently clipping')
    return {'fit_lo':lo,'fit_hi':hi,'seed':seed,'lower':lower,'upper':upper,
            'pedestal_sigma':ped,'incoming_average_scale':avg,'vov':vov,'layers_summed':layers}


def load_root(here):
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['ROOT_MAX_THREADS'] = '1'
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.DisableImplicitMT()
    ROOT.TF1.DefaultAddToGlobalList(False)
    ROOT.gInterpreter.ProcessLine('.O 2')
    if not ROOT.gInterpreter.Declare(f'#include "{(here/"models.hxx").as_posix()}"'):
        raise RuntimeError('ROOT could not compile benchmark helpers')
    ROOT.gSystem.Load('libMinuit2')
    ROOT.Math.MinimizerOptions.SetDefaultMinimizer('Minuit2','Migrad')
    ROOT.Math.MinimizerOptions.SetDefaultMaxFunctionCalls(1000)
    ROOT.Math.MinimizerOptions.SetDefaultMaxIterations(100)
    ROOT.Math.MinimizerOptions.SetDefaultTolerance(.01)
    for n in sorted({m[2] for m in METHODS if m[2]}):
        ROOT.lfhcal.convolution_benchmark.requireFFT(n)
    # Load the fitter and Python bindings before timing the real fits. This
    # analytic warm-up is not part of the convolution comparison.
    warm = ROOT.TH1D('warm_up_hist','',40,-4.,4.)
    warm.SetDirectory(0)
    for b in range(1,41):
        warm.SetBinContent(b,round(100*math.exp(-.5*warm.GetBinCenter(b)**2)))
    warm_function = ROOT.TF1('warm_up_function','gaus',-4.,4.)
    warm_function.SetParameters(100.,0.,1.)
    warm.Fit(warm_function,'QLSN0')
    return ROOT


def factory(R, case, method, tag):
    label, kind, points, expand = method
    lo,hi = case['fit_lo'],case['fit_hi']
    # Based on FIXED parameter bounds, never on Minuit's current trial widths.
    half = ((hi-lo)/2 + 8*case['upper'][3])*expand
    middle = (hi+lo)/2
    cLo,cHi = middle-half,middle+half
    f = R.lfhcal.convolution_benchmark.make(tag,kind,lo,hi,cLo,cHi,points)
    R.SetOwnership(f,True)
    for i in range(4):
        f.SetParameter(i,case['seed'][i])
        f.SetParLimits(i,case['lower'][i],case['upper'][i])
    return f,cLo,cHi


def selected_cells(code, histograms, calibrations, preset):
    if preset == 'smoke':
        return {cell:'named_smoke' for cell in SMOKE.get(code,())}
    out = {965:'control',1346:'control'}
    out.update({cell:'named_pathology' for cell in TARGETS.get(code,())})
    usable = [c for c,h in histograms.items()
              if c in calibrations and calibrations[c]['bc']>=2 and h.GetEntries()>0]
    if usable:
        ordered = sorted(usable,key=lambda c:(histograms[c].GetEntries(),c))
        for c,kind in ((ordered[0],'lowest_entries'),(ordered[-1],'highest_entries')):
            out[c] = out.get(c,kind)
    return out


def load_cases(R, repo, work, datasets, preset):
    cases = []
    for code in datasets:
        name = f'FullSet{code[0].upper()}_{code[1:]}'
        root = work/f'adaptive-fullset-{code}-repro'
        stem = f'rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{name}'
        hp = root/'refine5'/f'{stem}_Hists.root'
        cp = root/'refine4'/f'rawHGCROC_wPedwMuon_wBC_Imp4R_Muon_{name}_calib.txt'
        vov,avg,cals = read_calib(cp)
        mapping = repo/'configs/TB2026'/f'mapping_HGCROC_SPSH2TB_sumV{1 if code[0]=="g" else 2}_default.csv'
        segments = read_segments(mapping)
        rf = R.TFile.Open(str(hp),'READ')
        if not rf or rf.IsZombie():
            raise ValueError(f'Cannot open {hp}')
        try:
            directory = rf.Get('IndividualCellsTrigg')
            if not directory:
                raise ValueError(f'Missing IndividualCellsTrigg: {hp}')
            histograms = {}
            for cell in cals:
                h = directory.Get(f'hspectramipTriggADCCellID{cell}')
                if h:
                    histograms[cell] = h
            for cell,kind in sorted(selected_cells(code,histograms,cals,preset).items()):
                if cell not in histograms or cell not in segments:
                    raise ValueError(f'Missing requested histogram/mapping {code}:{cell}')
                h = histograms[cell].Clone(f'input_{code}_{cell}')
                h.SetDirectory(0)
                R.SetOwnership(h,True)
                # Native count-histogram convention only. No rebinning, rescaling,
                # error repair, or bin-integration changes hidden in this test.
                values = [float(h.GetBinContent(b)) for b in range(h.GetNbinsX()+2)]
                if any(not math.isfinite(v) or v<0 or abs(v-round(v))>1e-7 for v in values):
                    raise ValueError(f'Not an unweighted count histogram: {code}:{cell}')
                if any(abs(h.GetBinWidth(b)-1)>1e-10 for b in range(1,h.GetNbinsX()+1)):
                    raise ValueError(f'Expected native 1-ADC bins: {code}:{cell}')
                setup = original_setup(h,cals[cell]['ped'],avg,vov,segments[cell])
                archived = directory.Get(f'fmipmipTriggHGCellID{cell}')
                archived_parameters = [float(archived.GetParameter(i)) for i in range(4)] if archived else None
                bounds = list(R.lfhcal.convolution_benchmark.limits(archived)) if archived else None
                expected = [v for pair in zip(setup['lower'],setup['upper']) for v in pair]
                setup_difference = (max([abs(a-b) for a,b in zip(bounds,expected)]+
                    [abs(archived.GetXmin()-setup['fit_lo']),abs(archived.GetXmax()-setup['fit_hi'])])
                    if archived else None)
                # Prefer recorded range/bounds when present: exact same historical
                # setup for ALL engines; no need to trust a reconstruction there.
                if archived:
                    setup.update(fit_lo=float(archived.GetXmin()),fit_hi=float(archived.GetXmax()),
                                 lower=bounds[::2],upper=bounds[1::2])
                    area = int(h.Integral(h.FindBin(setup['fit_lo']),h.FindBin(setup['fit_hi'])))
                    setup['seed'] = [3*cals[cell]['ped'],avg,float(area),cals[cell]['ped']]
                if not all(a<v<b for a,v,b in zip(setup['lower'],setup['seed'],setup['upper'])):
                    raise ValueError(f'Input seed outside saved bounds for {code}:{cell}')
                centres = [float(h.GetBinCenter(b)) for b in range(1,h.GetNbinsX()+1)]
                digest = hashlib.sha256(json.dumps([centres,values],separators=(',',':')).encode()).hexdigest()
                cases.append(dict(setup,case_id=f'{code}:{cell}',dataset=code,cell=cell,category=kind,
                    histogram=h,input_path=str(hp),input_size=hp.stat().st_size,
                    input_mtime_ns=hp.stat().st_mtime_ns,counts_sha256=digest,refine4_path=str(cp),
                    refine4_sha256=hashlib.sha256(cp.read_bytes()).hexdigest(),
                    mapping_path=str(mapping),mapping_sha256=hashlib.sha256(mapping.read_bytes()).hexdigest(),
                    setup_source='saved_adaptive_tf1' if archived else 'reconstructed_original_rules',
                    reconstructed_setup_max_difference=setup_difference,
                    archived_parameters=archived_parameters,entries=float(h.GetEntries()),
                    nonfinite_stored_errors=sum(not math.isfinite(h.GetBinError(b)) for b in range(1,h.GetNbinsX()+1))))
        finally:
            rf.Close()
    return cases


def ref_function(R, case, params, span, name):
    method = (name, f'adaptive{span}',0,1.)
    f,_,_ = factory(R,case,method,name)
    for i,p in enumerate(params): f.SetParameter(i,p)
    return f


def coordinates(case, count=257):
    # Stagger interior samples to avoid checking only points commensurate with
    # the legacy sampling period. Always include the true histogram centres.
    lo,hi = case['fit_lo'],case['fit_hi']
    xs = [lo,hi]+[lo+(hi-lo)*(i+.37)/(count-1) for i in range(count-1)]
    h = case.get('histogram')
    if h:
        xs += [h.GetBinCenter(b) for b in range(1,h.GetNbinsX()+1) if lo<=h.GetBinCenter(b)<=hi]
    return sorted(set(xs))


def probe(R, case, params, label, methods):
    xs = coordinates(case)
    p = R.std.vector('double')(params)
    xv = R.std.vector('double')(xs)
    ref5 = ref_function(R,case,params,5,'probe_ref5')
    ref8 = ref_function(R,case,params,8,'probe_ref8')
    y5 = [ref5.Eval(x) for x in xs]
    y8 = [ref8.Eval(x) for x in xs]
    height = max(y8)
    rows = []
    for method in methods:
        name,kind,n,_ = method
        t0 = time.perf_counter()
        f,cLo,cHi = factory(R,case,method,'probe_'+name)
        for i,value in enumerate(params): f.SetParameter(i,value)
        f.Eval(xs[0])
        cold = time.perf_counter()-t0
        ys = [f.Eval(x) for x in xs]
        cache = R.lfhcal.convolution_benchmark.sweep(f,xv,p,3,False)
        changing = R.lfhcal.convolution_benchmark.sweep(f,xv,p,3,True)
        rows.append(dict(case_id=case['case_id'],probe=label,method=name,
             n_fft=n,conv_lo=cLo,conv_hi=cHi,grid_spacing=(cHi-cLo)/(n-1) if n else None,
             **dict(zip(PAR_NAMES,params)),cold_setup_and_first_eval_s=cold,
             cached_sweep_s=cache.seconds/3,changed_parameters_sweep_s=changing.seconds/3,
             evaluations_per_sweep=len(xs),minimum_value=min(ys),
             max_abs_error_over_peak_8=max(abs(a-b) for a,b in zip(ys,y8))/height,
             max_abs_error_over_peak_5=max(abs(a-b) for a,b in zip(ys,y5))/height,
             span5_vs_span8_over_peak=max(abs(a-b) for a,b in zip(y5,y8))/height))
    return rows


def fit_one(R, case, method, rep):
    label,kind,n,_ = method
    row = dict(case_id=case['case_id'],dataset=case['dataset'],cell=case['cell'],
               category=case['category'],entries=case['entries'],method=label,repeat=rep,
               setup_source=case['setup_source'],fit_lo=case['fit_lo'],fit_hi=case['fit_hi'])
    t0 = time.perf_counter()
    f,cLo,cHi = factory(R,case,method,f'fit_{case["dataset"]}_{case["cell"]}_{label}_{rep}')
    row.update(n_fft=n,conv_lo=cLo,conv_hi=cHi,grid_spacing=(cHi-cLo)/(n-1) if n else None)
    h = case['histogram'].Clone('fit_data')
    h.SetDirectory(0)
    R.SetOwnership(h,True)
    row['construction_wall_s'] = time.perf_counter()-t0
    t0,c0 = time.perf_counter(),time.process_time()
    try:
        result = h.Fit(f,FIT_OPTIONS)
        row.update(fit_wall_s=time.perf_counter()-t0,fit_cpu_s=time.process_time()-c0,status=int(result))
        r = result.Get()
        if not r: raise RuntimeError('ROOT returned no TFitResult')
        row.update(valid=bool(r.IsValid()),covariance_status=int(r.CovMatrixStatus()),
                   n_calls=int(r.NCalls()),edm=float(r.Edm()),min_fcn=float(r.MinFcnValue()),
                   root_chi2=float(f.GetChisquare()),ndf=int(f.GetNDF()))
        row['root_chi2_ndf'] = row['root_chi2']/row['ndf'] if row['ndf']>0 else None
        params = [float(f.GetParameter(i)) for i in range(4)]
        for i,name in enumerate(PAR_NAMES):
            row[name],row[name+'_err'] = params[i],float(f.GetParError(i))
            row[name+'_lo'],row[name+'_hi'] = case['lower'][i],case['upper'][i]
            for j in range(i,4): row[f'cov_{i}{j}'] = float(r.CovMatrix(i,j))
        row['bound_hits'] = sum(min(abs(p-a),abs(p-b))<1e-5 for p,a,b in zip(params,case['lower'],case['upper']))
        row['legacy_status_and_bounds_ok'] = row['status'] in (0,70,4000,4070) and row['bound_hits']==0
        row['strict_fit_ok'] = row['status']==0 and row['valid'] and row['covariance_status']==3 and row['bound_hits']==0
        measure = R.lfhcal.convolution_benchmark.measure(f,kind=='fft',cLo,cHi)
        row.update(scale_h=float(measure.peak),fwhm_h=float(measure.fwhm),peak_error=str(measure.error))
        ref8 = ref_function(R,case,params,8,'final_reference')
        reference_peak = R.lfhcal.convolution_benchmark.measure(ref8,False,0.,0.)
        row.update(reference8_scale_h=float(reference_peak.peak),reference8_fwhm_h=float(reference_peak.fwhm),
                   reference_peak_error=str(reference_peak.error))
        xs = coordinates(case)
        ys,yr = [f.Eval(x) for x in xs],[ref8.Eval(x) for x in xs]
        row['curve_max_abs_error_over_peak_8'] = max(abs(a-b) for a,b in zip(ys,yr))/max(yr)
        terms = []
        for b in range(1,h.GetNbinsX()+1):
            x = h.GetBinCenter(b)
            if case['fit_lo']<=x<=case['fit_hi']:
                observed,expected = h.GetBinContent(b),ref8.Eval(x)
                if expected<0 or (expected==0 and observed>0):
                    raise ValueError('Invalid expected count in common reference deviance')
                terms.append(2*(expected-observed+observed*math.log(observed/expected)) if observed else 2*expected)
        row['common_reference8_deviance'] = math.fsum(terms)
        row['common_reference8_ndf'] = len(terms)-4
        row['common_reference8_deviance_ndf'] = math.fsum(terms)/(len(terms)-4) if len(terms)>4 else None
        row['error'] = ''
    except Exception as exc:
        row.setdefault('fit_wall_s',time.perf_counter()-t0)
        row.setdefault('fit_cpu_s',time.process_time()-c0)
        row['error'] = str(exc)
    return row


def summarize(rows):
    out = {}
    for method in sorted({r['method'] for r in rows}):
        subset = [r for r in rows if r['method']==method]
        vals = lambda key: [float(r[key]) for r in subset if r.get(key) not in (None,'','?') and math.isfinite(float(r[key]))]
        times,errors = vals('fit_wall_s'),vals('curve_max_abs_error_over_peak_8')
        out[method] = {'attempts':len(subset), 'status_zero':sum(str(r.get('status'))=='0' for r in subset),
                       'strict_fit_ok':sum(str(r.get('strict_fit_ok')).lower()=='true' for r in subset),
                       'median_fit_s':statistics.median(times) if times else None,
                       'maximum_curve_error_over_peak':max(errors) if errors else None}
    # Compare PAIRED spectra/repeats, not ratios of unrelated overall medians.
    reference = {(r['case_id'],str(r['repeat'])):r for r in rows if r['method']=='adaptive5'}
    for method,stats in out.items():
        speed,mpv,scales = [],[],[]
        diffs = {k:[] for k in ('landau_width','gaussian_sigma','reference8_fwhm_h')}
        for r in rows:
            a = reference.get((r['case_id'],str(r['repeat'])))
            if r['method']!=method or a is None: continue
            try:
                if float(r['fit_wall_s'])>0: speed.append(float(a['fit_wall_s'])/float(r['fit_wall_s']))
                if str(r.get('strict_fit_ok')).lower()=='true' and str(a.get('strict_fit_ok')).lower()=='true':
                    mpv.append(abs(float(r['mpv'])-float(a['mpv']))/max(abs(float(a['mpv'])),1e-12))
                    for key in diffs:
                        u,v = float(r[key]),float(a[key])
                        if math.isfinite(u) and math.isfinite(v): diffs[key].append(abs(u-v))
                    u,v = float(r['reference8_scale_h']),float(a['reference8_scale_h'])
                    if math.isfinite(u) and math.isfinite(v): scales.append(abs(u-v))
            except (ValueError,TypeError,KeyError): pass
        stats.update(paired_median_speedup=statistics.median(speed) if speed else None,
                     common_strict_pairs=len(mpv),max_rel_mpv_change=max(mpv) if mpv else None,
                     max_reference_peak_change_adc=max(scales) if scales else None,
                     max_absolute_changes={k:max(v) if v else None for k,v in diffs.items()})
    return out


def self_test(R):
    case = dict(case_id='synthetic_control',fit_lo=-5.,fit_hi=100.,
                lower=[.1,1.,.01,.005],upper=[20.,80.,100.,10.],seed=[3.,30.,1.,5.])
    rows = probe(R,case,case['seed'],'ordinary',METHODS)
    fft = next(r for r in rows if r['method']=='fft65536')
    if fft['max_abs_error_over_peak_8']>1e-3:
        raise RuntimeError(f'Ordinary FFT normalization/phase smoke check failed: {fft}')
    # Check copy/lifetime safety of the small adapter and four-parameter order.
    f,_,_ = factory(R,case,METHODS[4],'copy_control')
    copy = f.Clone('copy_control_clone')
    R.SetOwnership(copy,True)
    before = copy.Eval(30.)
    del f
    copy.SetParameter(2,2.)
    if abs(copy.Eval(30.)/before-2.)>1e-10:
        raise RuntimeError('Area mapping or copied callback ownership failed')
    print(f'ROOT {R.gROOT.GetVersion()}: FFT backend, parameter order, normalization and lifetime smoke checks passed.')
    print('This is not validation across the allowed width domain; run --preset stress next.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path)
    ap.add_argument('--out',type=Path)
    ap.add_argument('--preset',choices=('smoke','survey','stress'),default='smoke')
    ap.add_argument('--datasets',nargs='+',choices=SETS)
    ap.add_argument('--repeats',type=int,default=3)
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--collect',type=Path)
    args = ap.parse_args()
    if args.collect:
        rows = []
        for p in sorted(args.collect.glob('*/fits.csv')):
            with p.open() as f: rows.extend(csv.DictReader(f))
        if not rows: ap.error('No per-dataset fits.csv found')
        write_csv(args.collect/'all-fits.csv',rows)
        summary = summarize(rows)
        write_json(args.collect/'summary.json',summary)
        print(json.dumps(clean(summary),indent=2));return
    here = Path(__file__).resolve().parent
    if args.repeats<1: ap.error('--repeats must be positive')
    if not args.self_test and not args.out: ap.error('--out is required')
    if args.out:
        args.out.mkdir(parents=True,exist_ok=True)
        if any(args.out.iterdir()): ap.error('Output directory must be empty; preserve earlier benchmarks')
    R = load_root(here)
    if args.self_test: self_test(R);return
    if args.preset=='stress':
        case = dict(case_id='synthetic',fit_lo=-20.,fit_hi=160.,lower=[.01,0.,.01,.001],
                    upper=[100.,120.,1e7,50.],seed=[3.,30.,1.,5.])
        rows = []
        for tag,params in (('ordinary',[3.,30.,1.,5.]),('narrow_landau',[.1,30.,1.,10.]),
                           ('very_narrow_landau',[.01,30.,1.,20.]),('tiny_gaussian',[10.,30.,1.,.005])):
            rows.extend(probe(R,case,params,tag,METHODS))
        write_csv(args.out/'probes.csv',rows)
        write_json(args.out/'environment.json',{'ROOT':R.gROOT.GetVersion(),'argv':sys.argv})
        print(f'Saved numerical stress tests: {args.out}/probes.csv');return
    if not args.work: ap.error('--work is required for real spectra')
    datasets = args.datasets or (tuple(SMOKE) if args.preset=='smoke' else SETS)
    cases = load_cases(R,here.parents[2],args.work,datasets,args.preset)
    if not cases: ap.error('Selected preset/datasets produced no cases')
    manifest = [{k:v for k,v in c.items() if k!='histogram'} for c in cases]
    def git(*command):
        try: return subprocess.check_output(['git','-C',str(here),*command],text=True,stderr=subprocess.DEVNULL).strip()
        except (OSError,subprocess.SubprocessError): return 'unavailable'
    write_json(args.out/'manifest.json',{'cases':manifest,'root_version':R.gROOT.GetVersion(),
        'git_commit':git('rev-parse','HEAD'),'git_status':git('status','--porcelain'),
        'host':socket.gethostname(),'platform':platform.platform(),'python':sys.version,'argv':sys.argv,
        'repeats':args.repeats,'fit_options':FIT_OPTIONS,'max_calls':1000,'max_iterations':100,'tolerance':.01,
        'methods':METHODS,'reference_numerics_base':BASE_COMMIT,
        'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (here/'benchmark.py',here/'models.hxx',here/'TF1Langau.h',here.parents[1]/'LangauNumerics.h')}})
    rows,probes = [],[]
    for case in cases:
        print(f'{case["case_id"]} {case["category"]}, {case["entries"]:g} entries',flush=True)
        params = case['archived_parameters'] or case['seed']
        probes.extend(probe(R,case,params,'archived' if case['archived_parameters'] else 'cold_seed',METHODS))
        write_csv(args.out/'probes.csv',probes)
        for rep in range(args.repeats):
            order = list(METHODS)
            random.Random(f'{case["case_id"]}:{rep}:20260928').shuffle(order)
            for method in order:
                row = fit_one(R,case,method,rep)
                rows.append(row)
                print(f'  {method[0]:18s} rep={rep} status={row.get("status","error")} {row["fit_wall_s"]:.3f}s',flush=True)
            write_csv(args.out/'fits.csv',rows)
    write_json(args.out/'summary.json',summarize(rows))
    print(f'Saved {len(rows)} fit attempts across {len(cases)} frozen spectra in {args.out}')


if __name__ == '__main__':
    main()
