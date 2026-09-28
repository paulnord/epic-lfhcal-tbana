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
# ROOT's TF1Convolution source squares an Int_t point count during normalization.
# Stay below sqrt(INT32_MAX). Odd grids reduce the parity-dependent error
# observed in the BNL fixed-parameter report (2026-09-28). The even/odd control
# remains in fft_grid_report.py. No curve shift or normalization fix is applied.
# fft16385_odd and fft32769_odd_wide have equal spacing and different padding.
MAX_SAFE_FFT_POINTS = 46340
METHODS = (('legacy100','legacy100',0,1.), ('adaptive5','adaptive5',0,1.),
           ('fft10001_odd','fft',10001,1.), ('fft16385_odd','fft',16385,1.),
           ('fft32769_odd','fft',32769,1.), ('fft32769_odd_wide','fft',32769,2.))
FIT_OPTIONS = 'QRLMNS0'  # production QRLMN0 plus S to retain TFitResult
BASE_COMMIT = '3a643646eb301c7112449e8f6d6ab31f12c72943'
PROGRESS_PATH = None


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)):
        return [clean(v) for v in value]
    return value


def write_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(clean(data), indent=2, allow_nan=False)+'\n')
    temp.replace(path)


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            row = clean(row)
            writer.writerow({k: '?' if row.get(k) is None else row[k] for k in fields})
    temp.replace(path)


def progress(stage, detail='', phase='checks', row=None):
    """Atomic checkpoints, outside fit timing; an external process enforces limits."""
    print(f'[{stage}] {detail}', flush=True)
    if PROGRESS_PATH is not None:
        if row is not None:
            write_json(PROGRESS_PATH.parent/'partial-fit.json', row)
        write_json(PROGRESS_PATH, dict(stage=stage, detail=detail, phase=phase,
                                      monotonic_s=time.monotonic(), pid=os.getpid()))


def finite_samples(values, label):
    values = [float(x) for x in values]
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError(f'{label}: nonfinite/empty curve; refusing to fit or certify it')
    return values


def curve_error(values, reference):
    values = finite_samples(values, 'candidate')
    reference = finite_samples(reference, 'reference')
    if len(values) != len(reference) or max(reference) <= 0:
        raise ValueError('Invalid reference length or peak height')
    result = max(abs(a-b) for a,b in zip(values,reference))/max(reference)
    if not math.isfinite(result):
        raise ValueError('Nonfinite curve discrepancy')
    return result


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
    """Original HGCROC improved/native-bin range and seed rules at BASE_COMMIT."""
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
    progress('ROOT startup', phase='startup')
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['ROOT_MAX_THREADS'] = '1'
    import ROOT
    ROOT.gROOT.SetBatch(True)
    if ROOT.IsImplicitMTEnabled():
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
    # Analytic fitter/binding warm-up is outside convolution fit timing.
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
    if kind == 'fft' and not 1000 <= points <= MAX_SAFE_FFT_POINTS:
        raise ValueError('Unsafe FFT point count: integer-square normalization may overflow')
    lo,hi = case['fit_lo'],case['fit_hi']
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


def load_cases(R, repo, work, datasets, preset, cells=None):
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
            chosen = selected_cells(code,histograms,cals,preset)
            if cells is not None:
                chosen = {c:chosen.get(c,'explicit') for c in cells}
            for cell,kind in sorted(chosen.items()):
                if cell not in histograms or cell not in segments:
                    raise ValueError(f'Missing requested histogram/mapping {code}:{cell}')
                h = histograms[cell].Clone(f'input_{code}_{cell}')
                h.SetDirectory(0)
                R.SetOwnership(h,True)
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
    lo,hi = case['fit_lo'],case['fit_hi']
    xs = [lo,hi]+[lo+(hi-lo)*(i+.37)/(count-1) for i in range(count-1)]
    h = case.get('histogram')
    if h:
        xs += [h.GetBinCenter(b) for b in range(1,h.GetNbinsX()+1) if lo<=h.GetBinCenter(b)<=hi]
    return sorted(set(xs))


def probe(R, case, params, label, methods):
    progress('probe reference', f'{case["case_id"]} {label}')
    xs = coordinates(case)
    p = R.std.vector('double')(params)
    xv = R.std.vector('double')(xs)
    ref5 = ref_function(R,case,params,5,'probe_ref5')
    ref8 = ref_function(R,case,params,8,'probe_ref8')
    y5 = finite_samples((ref5.Eval(x) for x in xs), 'reference5')
    y8 = finite_samples((ref8.Eval(x) for x in xs), 'reference8')
    span_error = curve_error(y5,y8)
    rows = []
    for method in methods:
        name,kind,n,_ = method
        progress('probe evaluator', f'{case["case_id"]} {label} {name}')
        t0 = time.perf_counter()
        f,cLo,cHi = factory(R,case,method,'probe_'+name)
        for i,value in enumerate(params): f.SetParameter(i,value)
        first = f.Eval(xs[0])
        cold = time.perf_counter()-t0
        finite_samples([first], name)
        ys = finite_samples((f.Eval(x) for x in xs), name)
        cache = R.lfhcal.convolution_benchmark.sweep(f,xv,p,3,False)
        changing = R.lfhcal.convolution_benchmark.sweep(f,xv,p,3,True)
        finite_samples([cache.checksum,changing.checksum], name+' timing sweeps')
        rows.append(dict(case_id=case['case_id'],probe=label,method=name,
             n_fft=n,conv_lo=cLo,conv_hi=cHi,grid_spacing=(cHi-cLo)/(n-1) if n else None,
             **dict(zip(PAR_NAMES,params)),cold_setup_and_first_eval_s=cold,
             cached_sweep_s=cache.seconds/3,changed_parameters_sweep_s=changing.seconds/3,
             evaluations_per_sweep=len(xs),minimum_value=min(ys),
             max_abs_error_over_peak_8=curve_error(ys,y8),
             max_abs_error_over_peak_5=curve_error(ys,y5),
             span5_vs_span8_over_peak=span_error))
    return rows


def fit_one(R, case, method, rep):
    label,kind,n,_ = method
    identity = f'{case["case_id"]} {label} rep={rep}'
    row = dict(case_id=case['case_id'],dataset=case['dataset'],cell=case['cell'],
               category=case['category'],entries=case['entries'],method=label,repeat=rep,
               setup_source=case['setup_source'],fit_lo=case['fit_lo'],fit_hi=case['fit_hi'])
    progress('construct', identity, phase='startup', row=row)
    t0 = time.perf_counter()
    f,cLo,cHi = factory(R,case,method,f'fit_{case["dataset"]}_{case["cell"]}_{label}_{rep}')
    row.update(n_fft=n,conv_lo=cLo,conv_hi=cHi,grid_spacing=(cHi-cLo)/(n-1) if n else None)
    h = case['histogram'].Clone('fit_data')
    h.SetDirectory(0)
    R.SetOwnership(h,True)
    row['construction_wall_s'] = time.perf_counter()-t0
    progress('fit', identity, phase='fit', row=row)
    t0,c0 = time.perf_counter(),time.process_time()
    try:
        result = h.Fit(f,FIT_OPTIONS)
        row.update(fit_wall_s=time.perf_counter()-t0,fit_cpu_s=time.process_time()-c0,status=int(result))
        progress('fit returned', f'{identity} status={row["status"]} {row["fit_wall_s"]:.3f}s', row=row)
        r = result.Get()
        if not r: raise RuntimeError('ROOT returned no TFitResult')
        row.update(valid=bool(r.IsValid()),covariance_status=int(r.CovMatrixStatus()),
                   n_calls=int(r.NCalls()),edm=float(r.Edm()),min_fcn=float(r.MinFcnValue()),
                   root_chi2=float(f.GetChisquare()),ndf=int(f.GetNDF()))
        row['root_chi2_ndf'] = row['root_chi2']/row['ndf'] if row['ndf']>0 else None
        params = finite_samples((f.GetParameter(i) for i in range(4)), 'fitted parameters')
        for i,name in enumerate(PAR_NAMES):
            row[name],row[name+'_err'] = params[i],float(f.GetParError(i))
            row[name+'_lo'],row[name+'_hi'] = case['lower'][i],case['upper'][i]
            for j in range(i,4): row[f'cov_{i}{j}'] = float(r.CovMatrix(i,j))
        row['bound_hits'] = sum(min(abs(p-a),abs(p-b))<1e-5 for p,a,b in zip(params,case['lower'],case['upper']))
        row['legacy_status_and_bounds_ok'] = row['status'] in (0,70,4000,4070) and row['bound_hits']==0
        row['strict_fit_ok'] = row['status']==0 and row['valid'] and row['covariance_status']==3 and row['bound_hits']==0
        progress('peak/FWHM', identity, row=row)
        measure = R.lfhcal.convolution_benchmark.measure(f,kind=='fft',cLo,cHi)
        row.update(scale_h=float(measure.peak),fwhm_h=float(measure.fwhm),peak_error=str(measure.error))
        progress('reference peak/FWHM', identity, row=row)
        ref8 = ref_function(R,case,params,8,'final_reference')
        reference_peak = R.lfhcal.convolution_benchmark.measure(ref8,False,0.,0.)
        row.update(reference8_scale_h=float(reference_peak.peak),reference8_fwhm_h=float(reference_peak.fwhm),
                   reference_peak_error=str(reference_peak.error))
        progress('curve validation', identity, row=row)
        xs = coordinates(case)
        ys,yr = [f.Eval(x) for x in xs],[ref8.Eval(x) for x in xs]
        row['curve_max_abs_error_over_peak_8'] = curve_error(ys,yr)
        progress('reference deviance', identity, row=row)
        terms = []
        for b in range(1,h.GetNbinsX()+1):
            x = h.GetBinCenter(b)
            if case['fit_lo']<=x<=case['fit_hi']:
                observed,expected = float(h.GetBinContent(b)),float(ref8.Eval(x))
                if not math.isfinite(expected) or expected<0 or (expected==0 and observed>0):
                    raise ValueError('Invalid expected count in common reference deviance')
                terms.append(2*(expected-observed+observed*math.log(observed/expected)) if observed else 2*expected)
        row['common_reference8_deviance'] = math.fsum(terms)
        row['common_reference8_ndf'] = len(terms)-4
        row['common_reference8_deviance_ndf'] = math.fsum(terms)/(len(terms)-4) if len(terms)>4 else None
        row['error'] = ''
        row['outcome'] = 'completed'
    except Exception as exc:
        # Only a returned/raised Fit call has a measured fit duration. A timeout
        # killed by the supervisor is recorded separately as a censored time.
        row.setdefault('fit_wall_s',time.perf_counter()-t0)
        row.setdefault('fit_cpu_s',time.process_time()-c0)
        row['error'] = str(exc)
        row['outcome'] = 'error'
    progress('attempt complete', identity, row=row)
    return row


def summarize(rows):
    out = {}
    for method in sorted({r['method'] for r in rows}):
        subset = [r for r in rows if r['method']==method]
        vals = lambda key: [float(r[key]) for r in subset if r.get(key) not in (None,'','?') and math.isfinite(float(r[key]))]
        times,errors = vals('fit_wall_s'),vals('curve_max_abs_error_over_peak_8')
        out[method] = {'attempts':len(subset), 'status_zero':sum(str(r.get('status'))=='0' for r in subset),
                       'strict_fit_ok':sum(str(r.get('strict_fit_ok')).lower()=='true' for r in subset),
                       'timeouts':sum(r.get('outcome')=='timeout' for r in subset),
                       'errors':sum(r.get('outcome') in ('error','crash') for r in subset),
                       'timed_fit_returns':len(times),
                       'median_fit_s':statistics.median(times) if times else None,
                       'maximum_curve_error_over_peak':max(errors) if errors else None}
    reference = {(r['case_id'],str(r['repeat'])):r for r in rows if r['method']=='adaptive5'}
    for method,stats in out.items():
        speed,mpv,scales = [],[],[]
        diffs = {k:[] for k in ('landau_width','gaussian_sigma','reference8_fwhm_h')}
        for r in rows:
            a = reference.get((r['case_id'],str(r['repeat'])))
            if r['method']!=method or a is None: continue
            try:
                rt,at = float(r['fit_wall_s']),float(a['fit_wall_s'])
                if rt>0 and at>=0 and math.isfinite(rt) and math.isfinite(at): speed.append(at/rt)
                if str(r.get('strict_fit_ok')).lower()=='true' and str(a.get('strict_fit_ok')).lower()=='true':
                    mpv.append(abs(float(r['mpv'])-float(a['mpv']))/max(abs(float(a['mpv'])),1e-12))
                    for key in diffs:
                        u,v = float(r[key]),float(a[key])
                        if math.isfinite(u) and math.isfinite(v): diffs[key].append(abs(u-v))
                    u,v = float(r['reference8_scale_h']),float(a['reference8_scale_h'])
                    if math.isfinite(u) and math.isfinite(v): scales.append(abs(u-v))
            except (ValueError,TypeError,KeyError): pass
        stats.update(paired_timing_pairs=len(speed),paired_median_speedup=statistics.median(speed) if speed else None,
                     common_strict_pairs=len(mpv),max_rel_mpv_change=max(mpv) if mpv else None,
                     max_reference_peak_change_adc=max(scales) if scales else None,
                     max_absolute_changes={k:max(v) if v else None for k,v in diffs.items()})
    return out


def self_test(R):
    case = dict(case_id='synthetic_control',fit_lo=-5.,fit_hi=100.,
                lower=[.1,1.,.01,.005],upper=[20.,80.,100.,10.],seed=[3.,30.,1.,5.])
    rows = probe(R,case,case['seed'],'ordinary',METHODS)
    # Save and report every candidate before raising on an accuracy failure.
    # The 0.1% target is unchanged; choosing an odd grid is not certification
    # of a narrow-width fit or permission to loosen this numerical check.
    if PROGRESS_PATH is not None:
        write_csv(PROGRESS_PATH.parent/'probes.csv', rows)
    progress('self-test accuracy', 'ordinary control; target=0.1% of peak')
    failures = []
    for row in rows:
        if row['n_fft']:
            error = row['max_abs_error_over_peak_8']
            passed = math.isfinite(error) and 0 <= error <= 1e-3
            status = 'PASS' if passed else 'FAIL'
            print(f'  {row["method"]}: {status}, max error/peak={error:.6g}',flush=True)
            if not passed:
                failures.append(row)
    if failures:
        raise RuntimeError(f'FFT normalization/phase smoke check failed: {failures}')
    # Exercise the C++ guard directly, before any overflowing ROOT arithmetic.
    try:
        R.lfhcal.fft_experiment.make('unsafe_grid',-5.,100.,-100.,200.,65536)
    except Exception:
        pass
    else:
        raise RuntimeError('C++ oversized-grid guard did not reject 65536')
    # Clone() serializes callback TF1s into sampled curves. Such a snapshot
    # is for plotting, not parameter changes. Exercise the live C++ copy
    # constructor instead; see COPY_LIFETIME.md and TF1::Copy in ROOT.
    progress('self-test copy/lifetime', 'live TF1 copy constructor (not Clone)')
    method = next(m for m in METHODS if m[0]=='fft32769_odd')
    f,_,_ = factory(R,case,method,'copy_control')
    original = float(f.Eval(30.))
    copy = R.TF1(f)
    copy.SetName('copy_control_live_copy')
    R.SetOwnership(copy,True)
    before = float(copy.Eval(30.))
    del f
    copy.SetParameter(2,2.)
    after = float(copy.Eval(30.))
    copy_ratio = before/original if original > 0 else None
    area_ratio = after/before if before > 0 else None
    diagnostic = dict(operation='TF1 copy constructor', original=original,
                      before=before, after=after, copy_ratio=copy_ratio,
                      area_ratio=area_ratio, expected_area_ratio=2., tolerance=1e-10)
    print(f'  live copy: original={original:.17g}, before={before:.17g}, '
          f'after={after:.17g}, copy ratio={copy_ratio}, area ratio={area_ratio}',flush=True)
    if PROGRESS_PATH is not None:
        write_json(PROGRESS_PATH.parent/'copy-lifetime.json', diagnostic)
    finite_samples([original,before,after],'copy/lifetime')
    if original<=0 or before<=0:
        raise RuntimeError(f'Nonpositive live-copy control: {diagnostic}')
    finite_samples([copy_ratio,area_ratio],'copy/lifetime ratios')
    if abs(copy_ratio-1.)>1e-10 or abs(area_ratio-2.)>1e-10:
        raise RuntimeError(f'Area mapping or live copied callback ownership failed: {diagnostic}')
    print(f'ROOT {R.gROOT.GetVersion()}: finite curves, safe FFT sizes, normalization and lifetime checks passed.')
    print('This is not validation across the allowed width domain; run --preset stress next.')


def main():
    global PROGRESS_PATH
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path)
    ap.add_argument('--out',type=Path)
    ap.add_argument('--preset',choices=('smoke','survey','stress'),default='smoke')
    ap.add_argument('--datasets',nargs='+',choices=SETS)
    ap.add_argument('--cells',nargs='+',type=int)
    ap.add_argument('--methods',nargs='+',choices=[m[0] for m in METHODS])
    ap.add_argument('--repeats',type=int,default=3)
    ap.add_argument('--repeat-offset',type=int,default=0)
    ap.add_argument('--prepare-only',action='store_true')
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--collect',type=Path)
    args = ap.parse_args()
    methods = [m for m in METHODS if not args.methods or m[0] in args.methods]
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
    if args.repeats<1 or args.repeat_offset<0: ap.error('Invalid repetition count/offset')
    if not args.self_test and not args.out: ap.error('--out is required')
    if args.out:
        args.out.mkdir(parents=True,exist_ok=True)
        if any(args.out.iterdir()): ap.error('Output directory must be empty; preserve earlier benchmarks')
        PROGRESS_PATH = args.out/'progress.json'
    R = load_root(here)
    if args.self_test: self_test(R);return
    if args.preset=='stress':
        case = dict(case_id='synthetic',fit_lo=-20.,fit_hi=160.,lower=[.01,0.,.01,.001],
                    upper=[100.,120.,1e7,50.],seed=[3.,30.,1.,5.])
        rows = []
        for tag,params in (('ordinary',[3.,30.,1.,5.]),('narrow_landau',[.1,30.,1.,10.]),
                           ('very_narrow_landau',[.01,30.,1.,20.]),('tiny_gaussian',[10.,30.,1.,.005])):
            rows.extend(probe(R,case,params,tag,methods))
            write_csv(args.out/'probes.csv',rows)
        write_json(args.out/'environment.json',{'ROOT':R.gROOT.GetVersion(),'argv':sys.argv})
        print(f'Saved numerical stress tests: {args.out}/probes.csv');return
    if not args.work: ap.error('--work is required for real spectra')
    datasets = args.datasets or (tuple(SMOKE) if args.preset=='smoke' else SETS)
    progress('read inputs', ','.join(datasets), phase='startup')
    cases = load_cases(R,here.parents[2],args.work,datasets,args.preset,args.cells)
    if not cases: ap.error('Selected preset/datasets produced no cases')
    manifest = [{k:v for k,v in c.items() if k!='histogram'} for c in cases]
    def git(*command):
        try: return subprocess.check_output(['git','-C',str(here),*command],text=True,stderr=subprocess.DEVNULL).strip()
        except (OSError,subprocess.SubprocessError): return 'unavailable'
    write_json(args.out/'manifest.json',{'cases':manifest,'root_version':R.gROOT.GetVersion(),
        'git_commit':git('rev-parse','HEAD'),'git_status':git('status','--porcelain'),
        'host':socket.gethostname(),'platform':platform.platform(),'python':sys.version,'argv':sys.argv,
        'repeats':args.repeats,'fit_options':FIT_OPTIONS,'max_calls':1000,'max_iterations':100,'tolerance':.01,
        'methods':methods,'reference_numerics_base':BASE_COMMIT,
        'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (here/'benchmark.py',here/'models.hxx',here/'TF1Langau.h',here.parents[1]/'LangauNumerics.h')}})
    if args.prepare_only:
        progress('selection complete', f'{len(cases)} frozen spectra',phase='startup')
        return
    rows,probes = [],[]
    for case in cases:
        print(f'{case["case_id"]} {case["category"]}, {case["entries"]:g} entries',flush=True)
        params = case['archived_parameters'] or case['seed']
        probes.extend(probe(R,case,params,'archived' if case['archived_parameters'] else 'cold_seed',methods))
        write_csv(args.out/'probes.csv',probes)
        # Separate pre-fit finite checks at the cold seed; no change to the
        # fitted function's cache or seed. Accuracy remains a reported diagnostic.
        if params != case['seed']:
            probes.extend(probe(R,case,case['seed'],'cold_seed',methods))
            write_csv(args.out/'probes.csv',probes)
        for rep in range(args.repeat_offset,args.repeat_offset+args.repeats):
            order = list(methods)
            random.Random(f'{case["case_id"]}:{rep}:20260928').shuffle(order)
            for method in order:
                row = fit_one(R,case,method,rep)
                rows.append(row)
                write_csv(args.out/'fits.csv',rows)
                write_json(args.out/'summary.json',summarize(rows))
                print(f'  {method[0]:18s} rep={rep} status={row.get("status","error")} {row["fit_wall_s"]:.3f}s',flush=True)
    progress('done',f'{len(rows)} attempts in {args.out}',phase='startup')


if __name__ == '__main__':
    main()
