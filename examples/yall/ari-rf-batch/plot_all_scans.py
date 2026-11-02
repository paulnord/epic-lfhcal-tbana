#!/usr/bin/env python3
"""Plot existing waveform measurements; never process events or change measurements."""
import argparse
import csv
import json
import math
import hashlib
import importlib.util
from pathlib import Path

CELLS = [base+i for base in (1152,1216,1408,1472,1536,1600,1792,1856) for i in range(8)]
RF_RUNS = [345,343,341,339,337,335,298,333,329,310,306,304,300]
GROUPS = [('RF',RF_RUNS),('CC',[353,347,298,349,351]),('CF',[361,355,363,298]),('CFComp',[355,357,359])]
METRICS = [('amplitude','Peak amplitude (arb. units)','hWaveformPeakAmplitudeVsCellID'),
           ('fwhm','FWHM (ns)','hWaveformFWHMVsCellID'),
           ('peak_time','Peak time (ns)','hWaveformPeakTimeVsCellID')]
EXPECTED = {298:(9,7,5,1),300:(1,7,5,1),304:(3,7,5,1),306:(4,7,5,1),310:(5,7,5,1),329:(6,7,5,1),333:(8,7,5,1),335:(10,7,5,1),337:(11,7,5,1),339:(12,7,5,1),341:(13,7,5,1),343:(14,7,5,1),345:(15,7,5,1),347:(9,7,4,1),349:(9,7,8,1),351:(9,7,10,1),353:(9,7,1,1),355:(9,5,5,1),357:(9,5,5,8),359:(9,5,5,15),361:(9,3,5,1),363:(9,5,5,1)}
# Recorded May scan, omitted by Ari's original macro. Include only existing data.
OPTIONAL_RF = {302:(2,7,5,1)}


def scan_groups(runs):
    available=set(runs)
    missing=set(EXPECTED)-available
    unknown=available-set(EXPECTED)-set(OPTIONAL_RF)
    if missing or unknown:
        raise ValueError(f'Unexpected run inventory: missing={sorted(missing)}, unknown={sorted(unknown)}')
    rf=sorted([r for r in available if r in RF_RUNS or r in OPTIONAL_RF],
              key=lambda r: (EXPECTED.get(r, OPTIONAL_RF.get(r))[0],r),reverse=True)
    return [('RF',rf)]+[(key,list(values)) for key,values in GROUPS[1:]]


def input_paths(rf, other, run302=None):
    paths={run:(rf if run in RF_RUNS else other)/
           f'products/waveform/calibratedHGCROC_wave_Run_{run}_Hists.root' for run in EXPECTED}
    candidate=run302 if run302 is not None else rf/'products/waveform/calibratedHGCROC_wave_Run_302_Hists.root'
    if run302 is not None or candidate.exists(): paths[302]=candidate
    return paths


def read_csv_measurements(path,settings):
    """Replay the exported measurements, never extract waveforms or replace blanks."""
    rows={}
    with path.open(newline='') as stream:
        for record in csv.DictReader(stream):
            run=int(record['run']); cell=int(record['cell']); status=int(record['status'])
            if run not in EXPECTED and run not in OPTIONAL_RF: raise ValueError(f'Unknown run {run}')
            if cell not in CELLS: raise ValueError(f'Unselected cell {cell}')
            if status not in range(-1,9): raise ValueError(f'Unknown status {status}')
            if any(int(record[k])!=int(settings[run][k]) for k in ('RF','CF','CC','CFComp')):
                raise ValueError(f'CSV settings differ from run database: {run}')
            row={'cell':cell,'status':status}
            for key,_,_ in METRICS:
                value=float(record[key]) if record[key].strip() else None
                valid=(status==0) if key=='fwhm' else (status==0 or status>=4)
                if valid != (value is not None): raise ValueError(f'CSV status/value mismatch: {run}/{cell}/{key}')
                if value is not None and (not math.isfinite(value) or (key!='peak_time' and value<=0)):
                    raise ValueError(f'Invalid saved measurement: {run}/{cell}/{key}')
                row[key]=value
            rows.setdefault(run,[]).append(row)
    scan_groups(rows)
    for run,records in rows.items():
        if len(records)!=len(CELLS) or {r['cell'] for r in records}!=set(CELLS):
            raise ValueError(f'Expected exactly one row per selected cell for run {run}')
        records.sort(key=lambda r: CELLS.index(r['cell']))
    return rows


def read_settings(path):
    lines=path.read_text().splitlines()
    header=next(i for i,line in enumerate(lines) if line.startswith('Run Number,'))
    rows={int(r['Run Number']):r for r in csv.DictReader(lines[header:])}
    for run,expected in {**EXPECTED,**OPTIONAL_RF}.items():
        actual=tuple(int(rows[run][name]) for name in ('RF','CF','CC','CFComp'))
        if actual != expected: raise ValueError(f'Run {run}: settings differ from verified scan definition')
    return rows


def read_measurements(ROOT,path,quality=None):
    f=ROOT.TFile.Open(str(path),'READ')
    if not f or f.IsZombie() or f.TestBit(ROOT.TFile.kRecovered):
        raise ValueError(f'Unreadable/recovered input: {path}')
    try:
        status=f.Get('hWaveformMeasurementStatusVsCellID')
        counts=f.Get('hWaveformMeasurementStatusCounts')
        if quality is not None:
            if not counts: raise ValueError(f'Missing aggregate quality counts: {path}')
            quality.update({'global_status_counts':{counts.GetXaxis().GetBinLabel(i) or str(i):int(counts.GetBinContent(i)) for i in range(1,11)},'global_boundary_peaks':int(counts.GetBinContent(10)),'note':'Aggregate HGCROCStudy counts; not restricted here to selected64cells.'})
        hist={key:f.Get(name) for key,title,name in METRICS}
        if not status or any(not h for h in hist.values()):
            raise ValueError(f'Missing saved measurement histograms: {path}')
        if any(not h.InheritsFrom('TH1') or h.GetNbinsX() <= max(CELLS) for h in [status,*hist.values()]):
            raise ValueError(f'Unexpected measurement histogram shape: {path}')
        rows=[]
        for cell in CELLS:
            # HGCROC_Waveform_Analysis stores status enum + 1; zero is unfilled.
            stored=float(status.GetBinContent(cell+1))
            if not math.isfinite(stored) or stored != int(stored):
                raise ValueError(f'Noninteger measurement status: {path} cell {cell}')
            code=int(stored)-1
            if code not in range(-1,9): raise ValueError(f'Unknown status {code}: {path} cell {cell}')
            has_peak=code==0 or code>=4
            row={'cell':cell,'status':code}
            for key,title,name in METRICS:
                valid=code==0 if key=='fwhm' else has_peak
                value=float(hist[key].GetBinContent(cell+1)) if valid else None
                if value is not None and not math.isfinite(value):
                    raise ValueError(f'Nonfinite saved valid measurement: {path} cell {cell}')
                if value is not None and key != 'peak_time' and value <= 0:
                    raise ValueError(f'Nonpositive saved valid measurement: {path} cell {cell}')
                row[key]=value
            rows.append(row)
        return rows
    finally: f.Close()


def quantile(values,q):
    v=sorted(values); p=q*(len(v)-1); low=int(p); high=math.ceil(p)
    return v[low]*(high-p)+v[high]*(p-low) if high!=low else v[low]


def box_summary(values):
    """Unbinned q*(n-1) quartiles and observed, inclusive 1.5-IQR whiskers."""
    if not values:
        return None
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Nonfinite box sample; never silently filter measurements')
    q1, median, q3 = [quantile(values, q) for q in (.25, .5, .75)]
    lower, upper = q1 - 1.5*(q3-q1), q3 + 1.5*(q3-q1)
    inside = [v for v in values if lower <= v <= upper]
    return dict(q1=q1, median=median, q3=q3, low=min(inside), high=max(inside),
                lower_fence=lower, upper_fence=upper)


def plot_range(summaries, values, metric, main):
    """One transparent axis per scan/metric, never a cut on the stored sample."""
    summaries = [s for s in summaries if s is not None]
    if not values:
        return 0., 1.
    if main:
        # Sparse interpolated quartiles can lie beyond observed whiskers.
        lo = min(min(s['low'], s['q1']) for s in summaries)
        hi = max(max(s['high'], s['q3']) for s in summaries)
    else:
        lo, hi = min(values), max(values)
    if not hi > lo:
        padding = max(1., .1*abs(lo))
        lo, hi = lo-padding, hi+padding
    span = hi-lo
    lo, hi = lo-.08*span, hi+.12*span
    if metric != 'peak_time' and min(values) >= 0.:
        lo = 0.
    return lo, hi


def offscale_counts(values, lo, hi):
    return sum(v < lo for v in values), sum(v > hi for v in values)


def draw(ROOT,rows,settings,out,groups=None):
    groups=GROUPS if groups is None else groups
    ROOT.gROOT.SetBatch(True); ROOT.gStyle.SetOptStat(0)
    ROOT.gStyle.SetPaperSize(25.33,32.)
    ROOT.gStyle.SetTitleFont(42,"XYZ"); ROOT.gStyle.SetLabelFont(42,"XYZ")
    root=ROOT.TFile(str(out/'HGCROC_AllScans.root'),'RECREATE')
    objects=[]
    try:
        # Keep the original full-range canvas and channel graph names intact.
        for main in (False, True):
            suffix='_main' if main else ''
            canvas=ROOT.TCanvas('all_hgcroc_scans'+suffix,'HGCROC settings scans',2400,1900)
            objects.append(canvas)
            for col,(parameter,runs) in enumerate(groups):
                for row,(key,title,name) in enumerate(METRICS):
                    top=1-row*.255; bottom=top-.255
                    pad=ROOT.TPad(f'pad_{col}_{row}{suffix}','',col*.25,bottom,(col+1)*.25,top)
                    objects.append(pad); pad.Draw(); pad.cd()
                    pad.SetLeftMargin(.19); pad.SetRightMargin(.045)
                    pad.SetBottomMargin(.18); pad.SetTopMargin(.15 if key=='fwhm' else .11)
                    values=[[r[key] for r in rows[run] if r[key] is not None] for run in runs]
                    summaries=[box_summary(vv) for vv in values]
                    allvalues=[v for vv in values for v in vv]
                    lo,hi=plot_range(summaries,allvalues,key,main)
                    frame=ROOT.TH1D(f'frame_{parameter}_{key}{suffix}',f';{parameter} setting;{title}',len(runs),.5,len(runs)+.5)
                    frame.SetDirectory(0); frame.SetMinimum(lo); frame.SetMaximum(hi)
                    frame.GetXaxis().SetLabelSize(.045); frame.GetXaxis().SetTitleSize(.045)
                    frame.GetYaxis().SetLabelSize(.04); frame.GetYaxis().SetTitleSize(.045)
                    frame.GetYaxis().SetTitleOffset(1.8); objects.append(frame)
                    for i,run in enumerate(runs,1):
                        code=int(settings[run][parameter]); label=str(code)
                        if parameter=='CF' and code==5: label=f'5 (R{run})'
                        frame.GetXaxis().SetBinLabel(i,label)
                    frame.Draw('AXIS')
                    text=ROOT.TLatex(); text.SetNDC(); text.SetTextFont(42); text.SetTextSize(.047)
                    text.DrawLatex(.19,.945,f'{parameter}: '+('main distribution' if main else 'full range'))
                    objects.append(text)
                    if key=='fwhm':
                        text.SetTextSize(.031)
                        # Same setting order as the x axis; missing widths remain missing.
                        text.DrawLatex(.19,.875,'Widths /64: '+', '.join(str(len(vv)) for vv in values))
                    if not allvalues:
                        text.SetTextSize(.045); text.DrawLatex(.25,.55,'No valid measurements')
                    for i,(run,vv,summary) in enumerate(zip(runs,values,summaries),1):
                        if not vv: continue
                        points=ROOT.TGraph(); outliers=ROOT.TGraph(); objects.extend([points,outliers])
                        for r in (r for r in rows[run] if r[key] is not None):
                            value=r[key]; x=i+.15*math.sin(.37*r['cell'])
                            if not main or lo <= value <= hi:
                                points.SetPoint(points.GetN(),x,value)
                                if value < summary['lower_fence'] or value > summary['upper_fence']:
                                    outliers.SetPoint(outliers.GetN(),x,value)
                        points.SetName(f'{"visible_channels" if main else "channels"}_{parameter}_{run}_{key}')
                        points.SetMarkerStyle(20); points.SetMarkerSize(.35)
                        points.SetMarkerColorAlpha(ROOT.kGray+2,.4)
                        if points.GetN(): points.Draw('P SAME')
                        root.cd(); points.Write(); pad.cd()
                        q1,med,q3=summary['q1'],summary['median'],summary['q3']
                        low,high=summary['low'],summary['high']
                        box=ROOT.TBox(i-.25,q1,i+.25,q3)
                        box.SetFillColorAlpha(ROOT.kAzure-9,.45); box.SetLineColor(ROOT.kBlue+2)
                        box.Draw(); objects.append(box)
                        for x1,y1,x2,y2 in [(i-.25,med,i+.25,med),(i,low,i,q1),(i,q3,i,high),(i-.1,low,i+.1,low),(i-.1,high,i+.1,high)]:
                            line=ROOT.TLine(x1,y1,x2,y2); line.Draw(); objects.append(line)
                        outliers.SetName(f'outliers_{parameter}_{run}_{key}{suffix}')
                        outliers.SetMarkerStyle(27); outliers.SetMarkerSize(.8)
                        outliers.SetMarkerColor(ROOT.kOrange+7); outliers.SetLineColor(ROOT.kOrange+7)
                        if outliers.GetN(): outliers.Draw('P SAME')
                        root.cd(); outliers.Write(); pad.cd()
                        if main:
                            below,above=offscale_counts(vv,lo,hi)
                            for count,up in ((below,False),(above,True)):
                                if not count: continue
                                span=hi-lo
                                begin,end=(hi-.12*span,hi-.035*span) if up else (lo+.12*span,lo+.035*span)
                                arrow=ROOT.TArrow(i,begin,i,end,.006,'|>')
                                arrow.SetLineColor(ROOT.kOrange+7); arrow.SetFillColor(ROOT.kOrange+7)
                                arrow.Draw(); objects.append(arrow)
                                label=ROOT.TLatex(i+.12,hi-.08*span if up else lo+.07*span,str(count))
                                label.SetTextFont(42); label.SetTextColor(ROOT.kOrange+7); label.SetTextSize(.038)
                                label.Draw(); objects.append(label)
                    canvas.cd()
                footer=ROOT.TPad(f'footer_{col}{suffix}','',col*.25,0,(col+1)*.25,.23)
                footer.Draw(); footer.cd(); objects.append(footer)
                text=ROOT.TLatex(); text.SetNDC(); text.SetTextFont(42); text.SetTextSize(.060); objects.append(text)
                fixed={'RF':['CF7, CC5, CFComp1'],'CC':['RF9 (8.89 k#Omega), CF7, CFComp1'],'CF':['RF9 (8.89 k#Omega), CC5, CFComp1','CF5 repeats: R355 and R363 kept separate'],'CFComp':['RF9 (8.89 k#Omega), CF5, CC5']}[parameter]
                labels=[f'Varied: {parameter}; fixed: '+fixed[0]]+fixed[1:]
                if parameter=='RF':
                    labels+=['RF code #rightarrow resistance (k#Omega):']
                    mapping=[f'{settings[r]["RF"]}: {80/int(settings[r]["RF"]):.3g}' for r in runs]
                    labels+=['; '.join(mapping[i:i+4]) for i in range(0,len(mapping),4)]
                labels+=['Box: unbinned IQR; line: median',
                         'Whiskers: observed within 1.5 IQR fences',
                         'Orange diamonds: outliers, NOT exclusions']
                if main:
                    labels+=['Arrows: actual off-scale counts (see full range)',
                             'Axis: boxes/whiskers + 8%/12% padding']
                else:
                    labels+=['Every valid value retained; no extra cuts']
                labels+=['Widths conditional on extraction success',
                         'Axes independent; compare numeric values']
                # RF has the longest footer; scale all four consistently to fit.
                for i,label in enumerate(labels): text.DrawLatex(.04,.95-i*.073,label)
                canvas.cd()
            root.cd(); canvas.Write()
            basename='HGCROC_AllScansMain' if main else 'HGCROC_AllScans'
            canvas.SaveAs(str(out/(basename+'.pdf'))); canvas.SaveAs(str(out/(basename+'.png')))
    finally:
        root.Close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rf-workspace',type=Path);p.add_argument('--other-workspace',type=Path)
    p.add_argument('--run302-input',type=Path,help='Already-analyzed run302 histogram file; otherwise auto-discover in RF workspace')
    p.add_argument('--measurements-csv',type=Path,help='Replay a complete exported 22/23-run measurement CSV without extraction')
    p.add_argument('--rundb',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--input-manifest',type=Path)
    p.add_argument('--rf-diagnostics',action='store_true',help='Also write native ROOT resistance summaries and nominal channel maps/comparisons')
    p.add_argument('--mapping',type=Path,default=Path(__file__).resolve().parents[3]/'configs/TB2026/mapping_HGCROC_SPSH2TB_sumV2_default.csv')
    p.add_argument('--summary-module',type=Path,default=Path(__file__).with_name('root_rf_summary.py'),help=argparse.SUPPRESS)
    p.add_argument('--channel-module',type=Path,default=Path(__file__).with_name('root_rf_channels.py'),help=argparse.SUPPRESS)
    a=p.parse_args()
    if a.measurements_csv:
        if a.rf_workspace or a.other_workspace or a.run302_input or a.input_manifest:
            p.error('--measurements-csv cannot be mixed with waveform-workspace inputs')
    elif a.rf_workspace is None or a.other_workspace is None:
        p.error('Both --rf-workspace and --other-workspace are required without --measurements-csv')
    prepared=None
    if a.input_manifest:
        prepared=json.loads(a.input_manifest.read_text())
        if len({int(i['run']) for i in prepared['inputs']})!=len(prepared['inputs']):
            p.error('Duplicate run in preparation manifest')
        for relative,expected_hash in prepared.get('code_sha256',{}).items():
            path=Path(prepared['repo'])/relative
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash:
                p.error('Source/configuration changed since preparation: '+str(path))
        for item in prepared['inputs']:
            st=Path(item['path']).stat()
            if (st.st_size,st.st_mtime_ns)!=(item['size_bytes'],item['mtime_ns']):
                p.error('Input changed since preparation: '+item['path'])
    if a.output.exists():p.error('Output exists; use a fresh directory')
    settings=read_settings(a.rundb)
    import ROOT
    rows={};inputs={};quality={}
    if a.measurements_csv:
        rows=read_csv_measurements(a.measurements_csv,settings)
        inputs={'measurements_csv':str(a.measurements_csv.resolve())}
    else:
        # A prepared job uses the frozen inventory, not newly appeared files.
        paths=({int(i['run']):Path(i['path']) for i in prepared['inputs']} if prepared
               else input_paths(a.rf_workspace,a.other_workspace,a.run302_input))
        if prepared and a.run302_input is not None and paths.get(302)!=a.run302_input:
            p.error('run302 path differs from frozen preparation manifest')
        scan_groups(paths)
        for run,path in paths.items():
            quality[run]={};rows[run]=read_measurements(ROOT,path,quality[run]);inputs[run]=str(path.resolve())
    groups=scan_groups(rows)
    a.output.mkdir(parents=True)
    draw(ROOT,rows,settings,a.output,groups)
    with (a.output/'measurements.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['run','RF','CF','CC','CFComp','cell','status','amplitude','fwhm','peak_time']);writer.writeheader()
        for run in [*EXPECTED,*sorted(set(rows)-set(EXPECTED))]:
            for row in rows[run]:writer.writerow({'run':run,**{k:settings[run][k] for k in ('RF','CF','CC','CFComp')},**row})
    (a.output/'inputs.json').write_text(json.dumps({'inputs':inputs,'quality':quality,'groups':groups,'note':'Saved measurements reused unchanged. CF5 repeats kept separate; channel spread is not uncertainty on a mean.'},indent=2)+'\n')
    if a.rf_diagnostics:
        modules=[]
        for path in (a.summary_module,a.channel_module):
            spec=importlib.util.spec_from_file_location(path.stem,path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);modules.append(module)
        modules[0].draw(ROOT,rows,settings,a.output,groups=groups)
        modules[1].draw(ROOT,rows,settings,a.output,a.mapping,groups=groups)
        sources=[Path(__file__).resolve(),a.summary_module,a.channel_module,a.rundb,a.mapping]
        if a.measurements_csv: sources.append(a.measurements_csv)
        if a.input_manifest: sources.append(a.input_manifest)
        metadata={'ROOT_version':ROOT.gROOT.GetVersion(),'source_sha256':{str(path.resolve()):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},'groups':groups,'run302_included':302 in rows,'mapping_note':'Nominal configuration geometry; installed hardware identity and embedded Setup independently unverified. R=80/code kOhm is provisional H2GCROC3B.','measurement_note':'Saved per-channel mean-waveform metrics; finite per-metric samples retained, no event reprocessing or new cuts.'}
        (a.output/'rf_diagnostics_provenance.json').write_text(json.dumps(metadata,indent=2)+'\n')
        for name in ('HGCROC_RFResistance.root','HGCROC_RFChannels.root'):
            result=ROOT.TFile.Open(str(a.output/name),'UPDATE')
            if not result or result.IsZombie(): raise OSError('Cannot save ROOT provenance: '+name)
            try:
                ROOT.TObjString(json.dumps(metadata,sort_keys=True)).Write('rf_diagnostics_provenance_json')
            finally: result.Close()

if __name__=='__main__':main()
