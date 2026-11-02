#!/usr/bin/env python3
"""Native ROOT RF summaries from saved channel measurements, without event processing.

Public entry point: draw(ROOT, rows, settings, out, groups=None).
The pure summarize helper needs no ROOT. All finite values are retained per metric;
status never vetoes a finite amplitude/time. H2GCROC3B R[kOhm]=80/RFcode is
provisional: the installed chip revision has not been established.
"""
import json
import math
import statistics
from collections import Counter
from pathlib import Path

CELLS = [base + i for base in (1152, 1216, 1408, 1472, 1536, 1600, 1792, 1856) for i in range(8)]
METRICS = [('amplitude', 'ADC amplitude (arb. units)'), ('fwhm', 'FWHM (ns)'), ('peak_time', 'Peak time (ns)')]
PROVISIONAL = 'PROVISIONAL H2GCROC3B: R = 80/RFcode k#Omega; installed chip revision unverified'


def finite_value(value):
    """Missing and nonfinite measurements are unavailable, never replaced by zero."""
    return value is not None and math.isfinite(float(value))


def select_runs(rows, settings, groups=None):
    """Discover the fixed-CF7/CC5/CFComp1 RF family, including newly supplied runs.

    A legacy groups list can document known RF membership but cannot suppress a
    newly available matching run (e.g. run 302 / RF2). No run numbers are hardcoded.
    """
    available = {int(run): rr for run, rr in rows.items()}
    settings = {int(run): value for run, value in settings.items()}
    declared = set()
    if groups is not None:
        group_map = dict(groups)
        declared = {int(run) for run in group_map.get('RF', [])}
    selected = []
    for run in available:
        if run not in settings:
            raise ValueError(f'Missing run settings: {run}')
        s = settings[run]
        fixed = tuple(int(s[k]) for k in ('CF', 'CC', 'CFComp'))
        if fixed != (7, 5, 1):
            if run in declared:
                raise ValueError(f'Declared RF run {run} does not have fixed CF7/CC5/CFComp1')
            continue
        code = int(s['RF'])
        if not 1 <= code <= 15:
            raise ValueError(f'Run {run}: RF code must be in [1,15], got {code}')
        cells = [int(r['cell']) for r in available[run]]
        if len(cells) != 64 or set(cells) != set(CELLS):
            raise ValueError(f'Run {run}: expected each of the 64 Ari cells exactly once')
        selected.append(run)
    if not selected:
        raise ValueError('No available RF runs with fixed CF7/CC5/CFComp1')
    return sorted(selected, key=lambda run: (80.0 / int(settings[run]['RF']), run))


def summarize(rows, settings, groups=None):
    """Full-precision mean/median/count/range per run, using identical finite sets."""
    rows = {int(run): rr for run, rr in rows.items()}
    settings = {int(run): value for run, value in settings.items()}
    runs = select_runs(rows, settings, groups)
    result = {'schema_version': 1, 'renderer': 'native ROOT TCanvas/TGraph/TLegend/TLatex',
              'mapping': {'model': 'H2GCROC3B', 'resistance_kOhm': '80/RFcode', 'provisional': True,
                          'installed_chip_revision_verified': False},
              'fixed_settings': {'CF': 7, 'CC': 5, 'CFComp': 1},
              'population': 'Measurements extracted from the per-channel mean waveforms, not event-level distributions',
              'selection': 'All finite values independently per metric; no status veto, outlier cuts, imputation, fits or error bars',
              'spread_note': 'Across-channel spread is not uncertainty on a mean',
              'runs': [], 'finite_totals': {key: 0 for key, _ in METRICS}}
    for run in runs:
        rr = rows[run]
        item = {'run': run, 'RFcode': int(settings[run]['RF']),
                'resistance_kOhm': 80.0 / int(settings[run]['RF']), 'records': len(rr),
                'status_counts': dict(sorted(Counter(str(int(r['status'])) for r in rr).items())), 'metrics': {}}
        for key, _ in METRICS:
            values = [float(r[key]) for r in rr if finite_value(r.get(key))]
            count = len(values)
            item['metrics'][key] = {'n': count, 'unavailable': len(rr)-count,
                                    'mean': statistics.mean(values) if count else None,
                                    'median': statistics.median(values) if count else None,
                                    'min': min(values) if count else None, 'max': max(values) if count else None}
            result['finite_totals'][key] += count
        result['runs'].append(item)
    return result


def value_range(values):
    if not values:
        return 0.0, 1.0
    lo, hi = min(values), max(values)
    pad = max((hi-lo)*.10, .5)
    return lo-pad, hi+pad


def draw(ROOT, rows, settings, out, groups=None):
    """Write a separate native ROOT RF product family; leave all-scans untouched.

    Produces HGCROC_RFResistance.root, a three-page .pdf, first-page .png,
    _channels.png, _audit.png, and _summary.json. Returns the JSON-compatible
    summary, including panel bounds/counts for independent clipping checks.
    Graphs are plain TGraph (not TGraphErrors); x coordinates are numerical kOhm.
    """
    rows = {int(run): rr for run, rr in rows.items()}
    summary = summarize(rows, settings, groups)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    # ROOT's PDF backend uses an A4 media box; oversized paper dimensions clip.
    ROOT.gStyle.SetPaperSize(27.0, 19.0)
    ROOT.gStyle.SetTitleFont(42, 'XYZ'); ROOT.gStyle.SetLabelFont(42, 'XYZ')
    keep = []
    blue, orange, gray = ROOT.kAzure+2, ROOT.kOrange+7, ROOT.kGray+2
    root = ROOT.TFile(str(out/'HGCROC_RFResistance.root'), 'RECREATE')
    if not root or root.IsZombie():
        raise OSError('Could not create RF resistance ROOT output')
    panels = []

    def text(target, x, y, label, size=.020, color=1, bold=False, align=11):
        target.cd()
        t = ROOT.TLatex(); t.SetNDC(); t.SetTextFont(62 if bold else 42)
        t.SetTextSize(size); t.SetTextColor(color); t.SetTextAlign(align)
        t.DrawLatex(x, y, label); keep.append(t)
        return t

    def graph(name, points, color, style, size):
        g = ROOT.TGraph(); g.SetName(name); g.SetTitle(name)
        for i, (x, y) in enumerate(points): g.SetPoint(i, x, y)
        g.SetMarkerColor(color); g.SetLineColor(color); g.SetMarkerStyle(style); g.SetMarkerSize(size)
        keep.append(g); root.cd(); g.Write()
        return g

    def canvas(name, title, subtitle, page):
        c = ROOT.TCanvas(name, title, 1800, 1280); keep.append(c)
        text(c, .055, .95, title, .034, bold=True)
        text(c, .055, .916, subtitle, .019, gray)
        text(c, .055, .879, PROVISIONAL, .021, orange, True)
        text(c, .055, .025, 'LFHCal RF scan | Saved channel measurements only | Native ROOT', .016, gray)
        text(c, .945, .025, f'{page} / 3', .016, gray, align=31)
        return c

    def pad(c, name, xy, key, xlim, ylim, bottom=False):
        c.cd(); p = ROOT.TPad(name, '', *xy); keep.append(p); p.Draw(); p.cd()
        p.SetLeftMargin(.16); p.SetRightMargin(.035); p.SetTopMargin(.055); p.SetBottomMargin(.24 if bottom else .18)
        p.SetGrid(1, 1); p.SetLogx(0); p.SetLogy(0)
        f = ROOT.TH1D('frame_'+name, '', 100, *xlim); f.SetDirectory(0)
        f.SetMinimum(ylim[0]); f.SetMaximum(ylim[1]); keep.append(f)
        for axis in [f.GetXaxis(), f.GetYaxis()]:
            axis.SetLabelFont(43); axis.SetTitleFont(43); axis.SetLabelSize(20); axis.SetTitleSize(22)
            axis.SetNdivisions(505); axis.SetTickLength(.02); axis.CenterTitle(True)
        f.GetYaxis().SetTitle(dict(METRICS)[key]); f.GetYaxis().SetTitleSize(18); f.GetYaxis().SetTitleOffset(2.5)
        f.GetXaxis().SetTitle('Provisional RF resistance (k#Omega) - linear axis' if bottom else '')
        f.GetXaxis().SetTitleSize(19); f.GetXaxis().SetTitleOffset(1.0)
        f.Draw('AXIS'); root.cd(); f.Write(); p.cd()
        return p

    base_graphs = {}
    try:
        for key, _ in METRICS:
            for stat, color, style in [('mean', blue, 20), ('median', orange, 25)]:
                points = [(s['resistance_kOhm'], s['metrics'][key][stat]) for s in summary['runs'] if s['metrics'][key][stat] is not None]
                base_graphs[key, stat] = graph(f'rf_{stat}_{key}', points, color, style, 1.0)
            graph(f'rf_finite_n_{key}', [(s['resistance_kOhm'], s['metrics'][key]['n']) for s in summary['runs']], gray, 20, .5)
            for s in summary['runs']:
                graph(f'rf_channels_run{s["run"]}_{key}', [(s['resistance_kOhm'], float(r[key])) for r in rows[s['run']] if finite_value(r.get(key))], gray, 20, .35)

        c1 = canvas('rf_resistance_summary', 'RF resistance means and medians',
                    f'{len(summary["runs"])} RF runs | CF7, CC5, CFComp1 held fixed | 64 Ari channels per run', 1)
        text(c1, .08, .829, 'Full resistance range', .024, bold=True)
        text(c1, .56, .829, 'Low resistance detail', .024, bold=True)
        low = [s for s in summary['runs'] if s['resistance_kOhm'] < 80.0]
        if not low: low = list(summary['runs'])
        omitted = [s['run'] for s in summary['runs'] if s not in low]
        text(c1, .56, .805, '80 k#Omega is outside this detail; retained at left.' if omitted else 'No setting omitted from this view.', .017, orange)
        full_x = (0.0, max(84.0, max(s['resistance_kOhm'] for s in summary['runs'])*1.05))
        low_values = [s['resistance_kOhm'] for s in low]
        low_pad = max((max(low_values)-min(low_values))*.06, .5)
        detail_x = (max(0.0, min(low_values)-low_pad), max(low_values)+low_pad)
        for i, (key, _) in enumerate(METRICS):
            y0, y1 = .60-i*.205, .795-i*.205
            for col, (series, xlim, view) in enumerate([(summary['runs'], full_x, 'full'), (low, detail_x, 'detail')]):
                values = [s['metrics'][key][stat] for s in series for stat in ('mean', 'median') if s['metrics'][key][stat] is not None]
                ylim = value_range(values)
                p = pad(c1, f'rf_summary_{view}_{key}', (.02+col*.49, y0, .51+col*.49, y1), key, xlim, ylim, i==2)
                for stat, color, style in [('mean', blue, 20), ('median', orange, 25)]:
                    g = graph(f'rf_{view}_{stat}_{key}', [(s['resistance_kOhm'], s['metrics'][key][stat]) for s in series if s['metrics'][key][stat] is not None], color, style, 1.0)
                    p.cd()
                    if g.GetN(): g.Draw('P SAME')
                panels.append({'page':1,'metric':key,'view':view,'xlim':list(xlim),'ylim':list(ylim),'runs':[s['run'] for s in series], 'omitted_by_x_view':omitted if col else [],'summary_values':len(values)})
        c1.cd(); legend = ROOT.TLegend(.055,.125,.41,.16); legend.SetBorderSize(0); legend.SetFillStyle(0); legend.SetTextFont(42); legend.SetTextSize(.019); legend.SetNColumns(2)
        legend.AddEntry(base_graphs['amplitude','mean'],'Arithmetic mean','p'); legend.AddEntry(base_graphs['amplitude','median'],'Median','p'); legend.Draw();keep.append(legend)
        text(c1,.055,.102,'Each marker summarizes measurements from per-channel mean waveforms, not an event-level distribution.',.019)
        text(c1,.055,.079,'Mean and median use the same finite set per metric. No finite outlier cuts, fits or error bars.',.019)
        text(c1,.055,.056,'Unavailable FWHM stays missing; finite amplitude/time remain. Across-channel spread is not uncertainty on a mean.',.018)

        c2 = canvas('rf_resistance_channels', 'All finite channel values', 'Full linear resistance and value ranges | No outlier removal | No horizontal jitter', 2)
        raw_refs = {}
        for i, (key, _) in enumerate(METRICS):
            normal, missing = [], []
            for s in summary['runs']:
                for r in rows[s['run']]:
                    if finite_value(r.get(key)):
                        (normal if finite_value(r.get('fwhm')) else missing).append((s['resistance_kOhm'], float(r[key])))
            allpoints = normal + missing
            ylim = value_range([y for _,y in allpoints])
            p = pad(c2, f'rf_raw_{key}', (.035,.605-i*.215,.965,.82-i*.215),key,full_x,ylim,i==2)
            allgraph = graph(f'rf_channels_{key}',allpoints,gray,20,.40)
            p.cd()
            if allgraph.GetN(): allgraph.Draw('P SAME')
            highlight = graph(f'rf_missing_width_channels_{key}',missing,orange,5,.9)
            p.cd()
            if highlight.GetN(): highlight.Draw('P SAME')
            for stat in ('mean','median'):
                g = base_graphs[key,stat]; p.cd()
                if g.GetN(): g.Draw('P SAME')
            text(p,.58,.86,f'n = {len(allpoints)} finite values',.072,gray,align=21)
            raw_refs[key] = (allgraph, highlight)
            assert all(full_x[0]<x<full_x[1] and ylim[0]<y<ylim[1] for x,y in allpoints)
            panels.append({'page':2,'metric':key,'view':'all finite channels','xlim':list(full_x),'ylim':list(ylim),'finite_values_drawn':len(allpoints),'missing_width_highlights':len(missing),'clipped_finite_values':0,'horizontal_jitter':False})
        c2.cd(); legend2=ROOT.TLegend(.055,.115,.925,.15);legend2.SetBorderSize(0);legend2.SetFillStyle(0);legend2.SetTextFont(42);legend2.SetTextSize(.018);legend2.SetNColumns(4)
        legend2.AddEntry(raw_refs['amplitude'][0],'Finite channel value','p');legend2.AddEntry(raw_refs['amplitude'][1],'Unavailable FWHM','p')
        legend2.AddEntry(base_graphs['amplitude','mean'],'Arithmetic mean','p');legend2.AddEntry(base_graphs['amplitude','median'],'Median','p');legend2.Draw();keep.append(legend2)
        text(c2,.055,.090,'Every finite value is plotted at its exact numerical resistance. Coincident points may overlap; none are cut.',.019)
        text(c2,.055,.066,'Orange crosses mark finite amplitude/time with unavailable FWHM. Across-channel spread is not uncertainty on a mean.',.018)

        c3=canvas('rf_resistance_audit','Data counts and definitions','Selected-record audit | Missing widths are unavailable, not zero | No cross-metric status veto',3)
        columns=[(.06,'Run'),(.14,'RF'),(.23,'R (k#Omega)'),(.36,'Records'),(.47,'Amp n'),(.59,'FWHM n'),(.71,'Time n'),(.85,'Statuses (code: n)')]
        for x,label in columns:text(c3,x,.819,label,.020,bold=True)
        nr=len(summary['runs']); step=min(.034,.455/max(nr,1))
        for i,s in enumerate(summary['runs']):
            m=s['metrics']; values=[str(s['run']),str(s['RFcode']),f'{s["resistance_kOhm"]:.6g}',str(s['records']),str(m['amplitude']['n']),str(m['fwhm']['n']),str(m['peak_time']['n']),', '.join(f'{k}: {v}' for k,v in s['status_counts'].items())]
            y=.780-i*step
            if i%2==0:
                c3.cd();box=ROOT.TBox(.05,y-.009,.96,y+.023);box.SetFillColor(ROOT.kGray);box.SetFillColorAlpha(ROOT.kGray,.10);box.SetLineColor(0);box.Draw();keep.append(box)
            for (x,_),v in zip(columns,values):text(c3,x,y,v,.019,orange if x==.59 and m['fwhm']['n']<64 else 1)
        total_y=.780-nr*step-.015
        text(c3,.06,total_y,'Total finite values',.020,bold=True)
        for x,key in [(.47,'amplitude'),(.59,'fwhm'),(.71,'peak_time')]:text(c3,x,total_y,str(summary['finite_totals'][key]),.020,bold=True)
        text(c3,.055,.265,'Status 0: valid width; 6: missing right crossing; 7: missing both crossings. Other codes are retained in JSON if present.',.018)
        text(c3,.055,.237,'Statistics use all finite values independently per metric, including finite values with nonzero extraction status.',.019)
        text(c3,.055,.208,'The 64 selected cells are Ari\'s fixed channel set. Run IDs are selected dynamically from available matching settings.',.019)
        text(c3,.055,.179,'Means and medians are across extracted per-channel mean-waveform measurements, not events.',.019)
        text(c3,.055,.150,'Channel spread is not uncertainty on a mean. No fits, error bars, outlier cuts, imputation or event processing.',.019)
        text(c3,.055,.115,'Mapping: DAQ H2GCROC3B implementation (h2gcalibx c559c954, config/h2gcroc_1v4_r2.json); not a designer specification.',.017,gray)
        text(c3,.055,.086,'Verify the installed chip revision before treating the provisional resistance values as installed-hardware values.',.019,orange)
        text(c3,.055,.057,'Exact statistics, status counts and panel bounds: HGCROC_RFResistance_summary.json',.018)

        summary['panels']=panels
        summary['mapping']['source_url']='https://gitlab.cern.ch/sjia/h2gcalibx/-/blob/c559c954110ad64b949f0d03ff7f5d68d22894c0/config/h2gcroc_1v4_r2.json'
        payload=json.dumps(summary,indent=2,allow_nan=False)
        root.cd(); metadata=ROOT.TObjString(payload);metadata.Write('rf_resistance_summary_json');keep.append(metadata)
        pdf=out/'HGCROC_RFResistance.pdf'
        for c,suffix in [(c1,''),(c2,'_channels'),(c3,'_audit')]:
            c.Modified();c.Update();root.cd();c.Write()
            c.SaveAs(str(out/f'HGCROC_RFResistance{suffix}.png'))
        c1.Print(str(pdf)+'(');c2.Print(str(pdf));c3.Print(str(pdf)+')')
        (out/'HGCROC_RFResistance_summary.json').write_text(payload+'\n')
    finally:
        root.Close()
    return summary
