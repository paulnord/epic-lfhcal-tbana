#!/usr/bin/env python3
"""Plot existing waveform measurements; never process events or change measurements."""
import argparse
import csv
import json
import math
from pathlib import Path

CELLS = [base+i for base in (1152,1216,1408,1472,1536,1600,1792,1856) for i in range(8)]
RF_RUNS = [345,343,341,339,337,335,298,333,329,310,306,304,300]
GROUPS = [('RF',RF_RUNS),('CC',[353,347,298,349,351]),('CF',[361,355,363,298]),('CFComp',[355,357,359])]
METRICS = [('amplitude','Peak amplitude (arb. units)','hWaveformPeakAmplitudeVsCellID'),
           ('fwhm','FWHM (ns)','hWaveformFWHMVsCellID'),
           ('peak_time','Peak time (ns)','hWaveformPeakTimeVsCellID')]
EXPECTED = {298:(9,7,5,1),300:(1,7,5,1),304:(3,7,5,1),306:(4,7,5,1),310:(5,7,5,1),329:(6,7,5,1),333:(8,7,5,1),335:(10,7,5,1),337:(11,7,5,1),339:(12,7,5,1),341:(13,7,5,1),343:(14,7,5,1),345:(15,7,5,1),347:(9,7,4,1),349:(9,7,8,1),351:(9,7,10,1),353:(9,7,1,1),355:(9,5,5,1),357:(9,5,5,8),359:(9,5,5,15),361:(9,3,5,1),363:(9,5,5,1)}


def read_settings(path):
    lines=path.read_text().splitlines()
    header=next(i for i,line in enumerate(lines) if line.startswith('Run Number,'))
    rows={int(r['Run Number']):r for r in csv.DictReader(lines[header:])}
    for run,expected in EXPECTED.items():
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


def draw(ROOT,rows,settings,out):
    ROOT.gROOT.SetBatch(True);ROOT.gStyle.SetOptStat(0)
    ROOT.gStyle.SetPaperSize(22.67,32.)
    ROOT.gStyle.SetTitleFont(42,"XYZ"); ROOT.gStyle.SetLabelFont(42,"XYZ")
    canvas=ROOT.TCanvas('all_hgcroc_scans','HGCROC settings scans',2400,1700)
    objects=[canvas]
    root=ROOT.TFile(str(out/'HGCROC_AllScans.root'),'RECREATE')
    try:
        for col,(parameter,runs) in enumerate(GROUPS):
            for row,(key,title,name) in enumerate(METRICS):
                top=1-row*.255; bottom=top-.255
                pad=ROOT.TPad(f'pad_{col}_{row}','',col*.25,bottom,(col+1)*.25,top)
                objects.append(pad);pad.Draw();pad.cd();pad.SetLeftMargin(.17);pad.SetBottomMargin(.17)
                values=[[r[key] for r in rows[run] if r[key] is not None] for run in runs]
                allvalues=[v for vv in values for v in vv]
                lo=min(allvalues) if allvalues else 0.;hi=max(allvalues) if allvalues else 1.
                span=max(hi-lo,1.);lo-=.08*span;hi+=.12*span
                if key!='peak_time':lo=min(lo,0.)
                frame=ROOT.TH1D(f'frame_{parameter}_{key}',f'{parameter} scan;{parameter} setting;{title}',len(runs),.5,len(runs)+.5)
                frame.SetDirectory(0);frame.SetMinimum(lo);frame.SetMaximum(hi)
                frame.GetXaxis().SetLabelSize(.035);frame.GetYaxis().SetTitleSize(.045);frame.GetYaxis().SetTitleOffset(1.7)
                objects.append(frame)
                for i,run in enumerate(runs,1):
                    code=int(settings[run][parameter]);label=str(code)
                    if parameter=='CF' and code==5:label=f'5 (R{run})'
                    frame.GetXaxis().SetBinLabel(i,label)
                frame.Draw('AXIS')
                for i,(run,vv) in enumerate(zip(runs,values),1):
                    if not vv:continue
                    points=ROOT.TGraph();objects.append(points)
                    for j,r in enumerate(r for r in rows[run] if r[key] is not None):
                        points.SetPoint(j,i+.15*math.sin(.37*r['cell']),r[key])
                    points.SetName(f'channels_{parameter}_{run}_{key}');points.SetMarkerStyle(20);points.SetMarkerSize(.3);points.SetMarkerColorAlpha(ROOT.kGray+2,.4);points.Draw('P SAME');root.cd();points.Write();pad.cd()
                    q1,med,q3=[quantile(vv,q) for q in (.25,.5,.75)]
                    box=ROOT.TBox(i-.25,q1,i+.25,q3);box.SetFillColorAlpha(ROOT.kAzure-9,.45);box.SetLineColor(ROOT.kBlue+2);box.Draw();objects.append(box)
                    for x1,y1,x2,y2 in [(i-.25,med,i+.25,med),(i,min(vv),i,q1),(i,q3,i,max(vv)),(i-.1,min(vv),i+.1,min(vv)),(i-.1,max(vv),i+.1,max(vv))]:
                        line=ROOT.TLine(x1,y1,x2,y2);line.Draw();objects.append(line)
                canvas.cd()
            footer=ROOT.TPad(f'footer_{col}','',col*.25,0,(col+1)*.25,.23);footer.Draw();footer.cd();objects.append(footer)
            text=ROOT.TLatex();text.SetNDC();text.SetTextSize(.065);objects.append(text)
            fixed={'RF':['CF7, CC5, CFComp1'],'CC':['RF9 (8.89 k#Omega), CF7, CFComp1'],'CF':['RF9 (8.89 k#Omega), CC5, CFComp1','CF5 repeats shown separately: R355, R363'],'CFComp':['RF9 (8.89 k#Omega), CF5, CC5']}[parameter]
            labels=[f'Varied: {parameter}','Fixed: '+fixed[0]]+fixed[1:]
            if parameter=='RF':
                labels+=['RF code #rightarrow resistance (k#Omega):']
                mapping=[f'{settings[r]["RF"]}: {80/int(settings[r]["RF"]):.3g}' for r in runs]
                labels+=['; '.join(mapping[i:i+4]) for i in range(0,len(mapping),4)]
            labels+=['Box: IQR; line: median; whiskers: full range','Points: channels; invalid widths omitted']
            for i,label in enumerate(labels):text.DrawLatex(.05,.95-i*.10,label)
            canvas.cd()
        root.cd();canvas.Write();canvas.SaveAs(str(out/'HGCROC_AllScans.pdf'));canvas.SaveAs(str(out/'HGCROC_AllScans.png'))
    finally:root.Close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rf-workspace',type=Path,required=True);p.add_argument('--other-workspace',type=Path,required=True)
    p.add_argument('--rundb',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--input-manifest',type=Path)
    a=p.parse_args()
    if a.input_manifest:
        for item in json.loads(a.input_manifest.read_text())['inputs']:
            st=Path(item['path']).stat()
            if (st.st_size,st.st_mtime_ns)!=(item['size_bytes'],item['mtime_ns']):
                p.error('Input changed since preparation: '+item['path'])
    if a.output.exists():p.error('Output exists; use a fresh directory')
    settings=read_settings(a.rundb)
    import ROOT
    rows={};inputs={};quality={}
    for run in EXPECTED:
        work=a.rf_workspace if run in RF_RUNS else a.other_workspace
        path=work/f'products/waveform/calibratedHGCROC_wave_Run_{run}_Hists.root'
        quality[run]={};rows[run]=read_measurements(ROOT,path,quality[run]);inputs[run]=str(path.resolve())
    a.output.mkdir(parents=True)
    draw(ROOT,rows,settings,a.output)
    with (a.output/'measurements.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['run','RF','CF','CC','CFComp','cell','status','amplitude','fwhm','peak_time']);writer.writeheader()
        for run in EXPECTED:
            for row in rows[run]:writer.writerow({'run':run,**{k:settings[run][k] for k in ('RF','CF','CC','CFComp')},**row})
    (a.output/'inputs.json').write_text(json.dumps({'inputs':inputs,'quality':quality,'groups':GROUPS,'note':'Saved measurements reused unchanged. CF5 repeats kept separate; channel spread is not uncertainty on a mean.'},indent=2)+'\n')

if __name__=='__main__':main()
