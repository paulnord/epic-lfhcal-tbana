#!/usr/bin/env python3
"""Native ROOT channel diagnostics from saved waveform measurements only.

No events, waveform extraction, new cuts, or Matplotlib. `draw` is called by the
existing plot_all_scans workflow. The only accepted spatial configuration is the
provenance-checked May sumV2 map. Its geometry is nominal: neither this file nor a
matching hash verifies the map embedded in earlier transfer ROOT products, the
installed ASIC revision, board serials, or electrical adjacency.

ROOT outputs contain editable TH2D/TH2I maps, TGraphs, canvases, and machine-readable
correlation matrices. Missing metric bins are NaN, never a zero-width surrogate;
separate status/finite-mask histograms disambiguate missing data. Every finite
amplitude/time is retained independently of width failure. Widths of 2-11 ns are
outlined as a diagnostic only, not excluded or declared scientifically invalid.
"""
import hashlib
import json
import math
from pathlib import Path
from statistics import mean

VERIFIED_MAPPING_SHA256 = '0d94c85012210baeec241b5fea4af7e74b28362450597b1948a82a176319477e'
METRICS = ('amplitude', 'fwhm', 'peak_time')
REFERENCE_RUN = 300
COMPARISON_RUNS = (304, 298)
STATUS_LABELS = {-1: 'Unfilled', 0: 'OK', 1: 'No profile', 2: 'Few bins',
                 3: 'No peak', 4: 'Sample', 5: 'Left', 6: 'Right', 7: 'Both', 8: 'Width'}


def finite(value):
    return value is not None and math.isfinite(value)


def average_ranks(values):
    """One-based ranks, averaging all ties; no external statistics dependency."""
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        for k in range(i, j):
            result[order[k]] = (i + 1 + j) / 2.0
        i = j
    return result


def pearson(a, b):
    if len(a) != len(b):
        raise ValueError('Correlation inputs have unequal lengths')
    if len(a) < 2:
        return None
    ma, mb = mean(a), mean(b)
    da = [x - ma for x in a]
    db = [x - mb for x in b]
    denominator = math.sqrt(sum(x*x for x in da) * sum(x*x for x in db))
    return sum(x*y for x, y in zip(da, db)) / denominator if denominator else None


def index_rows(rows):
    indexed = {}
    for row in rows:
        cell = int(row['cell'])
        if cell in indexed:
            raise ValueError('Duplicate cell ID: %s' % cell)
        indexed[cell] = row
    return indexed


def paired_values(reference, other, metric):
    """Return (cell, baseline value, reference value), with finite pairs only."""
    a, b = index_rows(reference), index_rows(other)
    if set(a) != set(b):
        raise ValueError('Same-channel comparison requires identical cell-ID sets')
    return [(cell, float(b[cell][metric]), float(a[cell][metric]))
            for cell in sorted(a) if finite(a[cell][metric]) and finite(b[cell][metric])]


def pair_statistics(reference, other, metric):
    pairs = paired_values(reference, other, metric)
    x = [p[1] for p in pairs]
    y = [p[2] for p in pairs]
    return {'n': len(pairs), 'pearson': pearson(x, y),
            'spearman': pearson(average_ranks(x), average_ranks(y))}


def select_rf_runs(rows, settings, groups=None):
    """Respect an explicit RF group; otherwise include supplied fixed-setting runs.

    This accepts run 302/RF2 when supplied, but never requires or fabricates it.
    """
    if groups is None:
        runs = [run for run in rows if run in settings and
                tuple(int(settings[run][k]) for k in ('CF', 'CC', 'CFComp')) == (7, 5, 1)]
    else:
        group_map = dict(groups)
        if 'RF' not in group_map:
            raise ValueError('Supplied groups have no RF group')
        runs = list(group_map['RF'])
    if len(set(runs)) != len(runs):
        raise ValueError('Duplicate RF run in group')
    for run in runs:
        if run not in rows or run not in settings:
            raise ValueError('Missing supplied measurements/settings for RF run %s' % run)
        if tuple(int(settings[run][k]) for k in ('CF', 'CC', 'CFComp')) != (7, 5, 1):
            raise ValueError('RF group changes a fixed setting in run %s' % run)
        if int(settings[run]['RF']) <= 0:
            raise ValueError('RF code must be positive for nominal 80/code labels')
    if REFERENCE_RUN not in runs or int(settings[REFERENCE_RUN]['RF']) != 1:
        raise ValueError('RF channel comparisons require supplied run 300 / RF1')
    return sorted(runs, key=lambda run: (int(settings[run]['RF']), run))


def load_geometry(mapping_path, cells):
    """Decode the verified production configuration; refuse an unknown map."""
    mapping_path = Path(mapping_path)
    digest = hashlib.sha256(mapping_path.read_bytes()).hexdigest()
    if digest != VERIFIED_MAPPING_SHA256:
        raise ValueError('Unverified nominal geometry map SHA256 %s; refusing guessed coordinates' % digest)
    mapping, readouts = {}, set()
    for line in mapping_path.read_text().splitlines():
        if not line.strip() or line.startswith(('#', 'sumOpt')):
            continue
        a = line.split()
        if len(a) != 11:
            raise ValueError('Unexpected mapping row format')
        asic, channel, layer, assembly, board_channel, row, col, module, mx, my, segment = a
        asic, channel, layer, row, col, module = map(int, (asic, channel, layer, row, col, module))
        cell = (module << 9) + (row << 8) + (col << 6) + layer
        if cell in mapping or (asic, channel) in readouts:
            raise ValueError('Nonunique geometry or readout address')
        readouts.add((asic, channel))
        mapping[cell] = dict(module=module, asic=asic, channel=channel, half=channel//36,
                             layer=layer, row=row, col=col, assembly=assembly,
                             x_cm=-7.5+5*col+float(mx), y_cm=-2.5+5*row+float(my))
    selected = {}
    for cell in cells:
        if cell not in mapping:
            raise ValueError('Cell not present in verified mapping: %s' % cell)
        g = mapping[cell]
        if (g['module'], g['asic']) not in ((2, 1), (3, 5)) or not 0 <= g['layer'] < 8:
            raise ValueError('Cell outside supported central 2x4 nominal geometry: %s' % cell)
        if g['x_cm'] not in (-7.5, -2.5, 2.5, 7.5) or g['y_cm'] not in (-2.5, 2.5):
            raise ValueError('Cell outside supported transverse slice: %s' % cell)
        g = dict(g)
        g['xbin'] = (-7.5, -2.5, 2.5, 7.5).index(g['x_cm']) + 1
        g['ybin'] = 16 - 2*g['layer'] - (0 if g['row'] == 1 else 1)
        selected[cell] = g
    if len({(g['xbin'], g['ybin']) for g in selected.values()}) != len(selected):
        raise ValueError('Nominal spatial bin collision')
    return selected


def _format(value):
    return 'undefined' if value is None else '%.3f' % value


def _text(ROOT, keep, x, y, text, size=.024, color=1, ndc=True, align=11):
    obj = ROOT.TLatex(x, y, str(text))
    obj.SetTextFont(42)
    obj.SetTextSize(size)
    obj.SetTextColor(color)
    obj.SetTextAlign(align)
    if ndc:
        obj.SetNDC()
    obj.Draw()
    keep.append(obj)
    return obj


def _canvas(ROOT, keep, name, title, subtitle, page):
    c = ROOT.TCanvas(name, title, 1800, 1200)
    c.SetFillColor(0)
    c.cd()
    keep.append(c)
    _text(ROOT, keep, .035, .955, title, .034)
    _text(ROOT, keep, .035, .917, subtitle, .020)
    _text(ROOT, keep, .035, .030,
          'Saved channel measurements only; no new cuts or event reprocessing. Geometry is configuration-derived.', .017)
    _text(ROOT, keep, .035, .010,
          'Provisional R = 80/RF code k#Omega; installed ASIC revision, board identity and transfer-ROOT map unverified.', .016)
    _text(ROOT, keep, .965, .012, str(page), .018, align=31)
    return c


def _write(root, obj):
    root.cd()
    obj.Write()


def _map_hist(ROOT, name, integer=False):
    cls = ROOT.TH2I if integer else ROOT.TH2D
    h = cls(name, '', 4, 0., 4., 16, 0., 16.)
    h.SetDirectory(0)
    h.SetStats(False)
    for i, label in enumerate(('M2 c2', 'M2 c3', 'M3 c0', 'M3 c1'), 1):
        h.GetXaxis().SetBinLabel(i, label)
    for layer in range(8):
        h.GetYaxis().SetBinLabel(16-2*layer, 'L%d r1' % layer)
        h.GetYaxis().SetBinLabel(15-2*layer, 'L%d r0' % layer)
    h.GetXaxis().SetLabelSize(.046)
    h.GetYaxis().SetLabelSize(.036)
    h.GetZaxis().SetLabelSize(.035)
    h.GetZaxis().SetTitleSize(.033)
    h.GetXaxis().SetTickLength(0)
    h.GetYaxis().SetTickLength(0)
    return h


def _map_page(ROOT, rows, settings, geometry, map_runs, metric, root, keep, page):
    is_status = metric == 'status'
    title = {'amplitude': 'RF peak amplitude in nominal channel geometry',
             'fwhm': 'RF widths and missing extractions by channel',
             'status': 'RF extraction status by channel'}[metric]
    units = {'amplitude': 'Peak amplitude (arb. units), shared logarithmic color scale',
             'fwhm': 'FWHM (ns), shared linear color scale; missing width is not zero',
             'status': 'Stored extraction status; finite widths of 2-11 ns are outlined, not excluded'}[metric]
    c = _canvas(ROOT, keep, 'rf_channels_'+metric, title,
                'CF7 / CC5 / CFComp1 fixed. Each nominal layer is a 2x4 slice; stacked slices are not physical depth distances.', page)
    vals = [float(r[metric]) for run in map_runs for r in rows[run] if not is_status and finite(r[metric])]
    vmin = min(vals) if vals else 0.
    vmax = max(vals) if vals else 1.
    if metric == 'amplitude' and vmin <= 0:
        raise ValueError('Amplitude logarithmic maps require positive finite values')
    if not vmax > vmin:
        vmax = vmin + 1.
    for column, run in enumerate(map_runs):
        c.cd()
        width = .93 / len(map_runs)
        x0 = .035 + column*width
        pad = ROOT.TPad('pad_%s_%s' % (metric, run), '', x0, .158, x0+width, .885)
        pad.SetLeftMargin(.18)
        pad.SetRightMargin(.16 if not is_status else .06)
        pad.SetBottomMargin(.07)
        pad.SetTopMargin(.12)
        pad.SetFillColor(0)
        pad.Draw()
        pad.cd()
        keep.append(pad)
        # Persist the palette as native ROOT paint-time state when a saved canvas is reopened.
        palette = ROOT.TExec('palette_%s_%s' % (metric, run), 'gStyle->SetPalette(kViridis);')
        keep.append(palette)
        h = _map_hist(ROOT, 'map_run%d_%s' % (run, metric), integer=is_status)
        valid = _map_hist(ROOT, 'finite_mask_run%d_%s' % (run, metric), integer=True)
        status = _map_hist(ROOT, 'status_map_run%d_%s' % (run, metric), integer=True)
        keep.extend([h, valid, status])
        if not is_status:
            for x in range(1, 5):
                for y in range(1, 17):
                    h.SetBinContent(x, y, float('nan'))
        for row in rows[run]:
            g = geometry[int(row['cell'])]
            x, y = g['xbin'], g['ybin']
            value = row['status'] if is_status else row[metric]
            h.SetBinContent(x, y, float(value) if finite(value) else float('nan'))
            valid.SetBinContent(x, y, 1 if finite(value) else 0)
            status.SetBinContent(x, y, int(row['status']))
        if is_status:
            h.Draw('AXIS')
        else:
            h.SetMinimum(vmin if metric == 'amplitude' else 0.)
            h.SetMaximum(vmax)
            if metric == 'amplitude':
                pad.SetLogz()
            h.Draw('COLZ')
        pad.GetListOfPrimitives().AddFirst(palette)
        for row in rows[run]:
            cell = int(row['cell'])
            g = geometry[cell]
            x, y = g['xbin']-1., g['ybin']-1.
            value = row['status'] if is_status else row[metric]
            missing = not finite(value)
            if is_status or missing:
                box = ROOT.TBox(x+.015, y+.015, x+.985, y+.985)
                if is_status:
                    color = ROOT.TColor.GetColor('#e7edee') if row['status'] == 0 else ROOT.TColor.GetColor('#eea5a0')
                    if row['status'] == 7:
                        color = ROOT.TColor.GetColor('#d65b52')
                else:
                    color = ROOT.TColor.GetColor('#eea5a0')
                box.SetFillColor(color)
                box.SetLineColor(ROOT.kWhite)
                box.Draw()
                keep.append(box)
            narrow = finite(row['fwhm']) and 2 <= row['fwhm'] <= 11
            if narrow and metric in ('fwhm', 'status'):
                border = ROOT.TBox(x+.04, y+.04, x+.96, y+.96)
                border.SetFillStyle(0)
                border.SetLineColor(ROOT.kMagenta+2)
                border.SetLineWidth(3)
                border.Draw()
                keep.append(border)
            if is_status:
                label = STATUS_LABELS[int(row['status'])]
                ink = ROOT.kBlack
            elif missing:
                label = STATUS_LABELS[int(row['status'])]+' missing'
                ink = ROOT.kBlack
            else:
                label = '%.1f' % value if metric == 'amplitude' else '%g' % value
                t = math.log(value/vmin)/math.log(vmax/vmin) if metric == 'amplitude' else value/vmax
                ink = ROOT.kWhite if t < .42 else ROOT.kBlack
            _text(ROOT, keep, x+.5, y+.69, cell, .023, ink, ndc=False, align=22)
            _text(ROOT, keep, x+.5, y+.28, label, .028 if not missing else .023, ink, ndc=False, align=22)
        boundary = ROOT.TLine(2., 0., 2., 16.)
        boundary.SetLineStyle(2)
        boundary.SetLineWidth(2)
        boundary.Draw()
        keep.append(boundary)
        for y in range(2, 16, 2):
            line = ROOT.TLine(0., float(y), 4., float(y))
            line.SetLineColor(ROOT.kWhite)
            line.SetLineWidth(2)
            line.Draw()
            keep.append(line)
        code = int(settings[run]['RF'])
        _text(ROOT, keep, .50, .968, 'RF%d / %.2f k#Omega / run %d' % (code, 80./code, run), .039, align=22)
        _text(ROOT, keep, .345, .919, 'Module 2 / ASIC 1', .025, align=22)
        _text(ROOT, keep, .675, .919, 'Module 3 / ASIC 5', .025, align=22)
        finite_n = sum(finite(r['fwhm']) for r in rows[run])
        narrow_n = sum(finite(r['fwhm']) and 2 <= r['fwhm'] <= 11 for r in rows[run])
        c.cd()
        _text(ROOT, keep, x0+width*.5, .143,
              'Widths %d/%d; 2-11 ns: %d' % (finite_n, len(rows[run]), narrow_n), .020, align=22)
        for obj in (h, valid, status):
            _write(root, obj)
    c.cd()
    _text(ROOT, keep, .035, .105, units, .022)
    if metric == 'amplitude':
        note = 'Tile labels: cell ID above saved value. All finite amplitudes retained, including peaks with failed width extraction.'
    elif metric == 'fwhm':
        note = 'Pink: missing crossing/width; magenta outline: retained finite 2-11 ns. Neither is a causal hardware diagnosis.'
    else:
        note = 'OK: status 0; Right: status 6, missing right crossing; Both: status 7, missing both. Other statuses use their stored labels.'
    _text(ROOT, keep, .035, .070, note, .020)
    return c


def _scatter_page(ROOT, rows, settings, geometry, comparisons, statistics, root, keep, page):
    c = _canvas(ROOT, keep, 'rf_channels_pairs', 'Same-channel comparisons against RF1',
                'Exact cell-ID joins. Full finite-value ranges; Pearson r uses raw values and Spearman #rho uses average tied ranks.', page)
    colors = {1: ROOT.kAzure+2, 5: ROOT.kOrange+7}
    for col, run in enumerate(comparisons):
        for row_number, metric in enumerate(('amplitude', 'fwhm')):
            x0 = .035 + col*.93/len(comparisons)
            width = .93/len(comparisons)
            y0 = .495 if row_number == 0 else .12
            c.cd()
            pad = ROOT.TPad('pair_pad_%s_%s' % (run, metric), '', x0, y0, x0+width, y0+.375)
            pad.SetLeftMargin(.14)
            pad.SetRightMargin(.04)
            pad.SetBottomMargin(.18)
            pad.SetTopMargin(.13)
            pad.Draw()
            pad.cd()
            keep.append(pad)
            pairs = paired_values(rows[REFERENCE_RUN], rows[run], metric)
            x = [p[1] for p in pairs]
            y = [p[2] for p in pairs]
            lo_x = min(0., min(x)) if x else 0.
            lo_y = min(0., min(y)) if y else 0.
            hi_x = max(x) if x else 1.
            hi_y = max(y) if y else 1.
            hi_x += max(1., .08*(hi_x-lo_x))
            hi_y += max(1., .08*(hi_y-lo_y))
            code = int(settings[run]['RF'])
            label, unit = ('Peak amplitude', 'arb. units') if metric == 'amplitude' else ('FWHM', 'ns')
            frame = ROOT.TH2D('pair_frame_%s_%s' % (run, metric),
                              ';RF%d %s (%s);RF1 %s (%s)' % (code, label, unit, label, unit),
                              1, lo_x, hi_x, 1, lo_y, hi_y)
            frame.SetDirectory(0)
            frame.SetStats(False)
            frame.GetXaxis().SetTitleSize(.055)
            frame.GetYaxis().SetTitleSize(.055)
            frame.GetXaxis().SetLabelSize(.045)
            frame.GetYaxis().SetLabelSize(.045)
            frame.GetYaxis().SetTitleOffset(1.15)
            frame.Draw('AXIS')
            keep.append(frame)
            all_points = ROOT.TGraph()
            all_points.SetName('paired_run300_run%d_%s' % (run, metric))
            all_points.SetTitle('RF1 same-cell values;baseline;RF1')
            by_asic = {}
            for asic in (1, 5):
                graph = ROOT.TGraph()
                graph.SetName('paired_run300_run%d_%s_asic%d' % (run, metric, asic))
                graph.SetMarkerStyle(20)
                graph.SetMarkerSize(.75)
                graph.SetMarkerColor(colors[asic])
                by_asic[asic] = graph
            narrow = ROOT.TGraph()
            narrow.SetName('paired_run300_run%d_%s_narrow' % (run, metric))
            narrow.SetMarkerStyle(24)
            narrow.SetMarkerSize(1.15)
            narrow.SetMarkerColor(ROOT.kMagenta+2)
            for cell, xx, yy in pairs:
                all_points.SetPoint(all_points.GetN(), xx, yy)
                graph = by_asic[geometry[cell]['asic']]
                graph.SetPoint(graph.GetN(), xx, yy)
                if metric == 'fwhm' and 2 <= yy <= 11:
                    narrow.SetPoint(narrow.GetN(), xx, yy)
            for graph in by_asic.values():
                if graph.GetN():
                    graph.Draw('P SAME')
            if narrow.GetN():
                narrow.Draw('P SAME')
            keep.extend([all_points, narrow, *by_asic.values()])
            s = statistics[str(run)][metric]
            _text(ROOT, keep, .14, .935,
                  'RF1 vs RF%d: n=%d, r=%s, #rho=%s' % (code, s['n'], _format(s['pearson']), _format(s['spearman'])), .042)
            for obj in [frame, all_points, narrow, *by_asic.values()]:
                _write(root, obj)
    c.cd()
    _text(ROOT, keep, .65, .888, 'Nominal ASIC 1', .020, colors[1])
    _text(ROOT, keep, .82, .888, 'Nominal ASIC 5', .020, colors[5])
    _text(ROOT, keep, .035, .083,
          'Nominal ASIC colors identify configuration groups, not measured coupling. Magenta rings: retained RF1 widths of 2-11 ns.', .020)
    _text(ROOT, keep, .035, .055,
          'Missing widths are absent from width pairs only; the corresponding finite amplitudes remain in amplitude pairs.', .020)
    return c


def _summary_page(ROOT, rows, settings, runs, statistics, root, keep, page):
    c = _canvas(ROOT, keep, 'rf_channels_correlations', 'RF1 matched-channel correlations across supplied RF settings',
                'n = finite same-cell pairs; Fail = missing width in the compared run. No outlier cuts; channel counts are not mean uncertainties.', page)
    headers = ['RF', 'R (k#Omega)', 'Run', 'Amp n', 'Amp r', 'Amp #rho', 'Width n', 'Width r', 'Width #rho', 'Fail', '2-11 ns']
    xs = [.055, .123, .208, .288, .375, .470, .570, .665, .760, .860, .935]
    for x, label in zip(xs, headers):
        _text(ROOT, keep, x, .852, label, .020, align=22)
    others = [r for r in runs if r != REFERENCE_RUN]
    spacing = min(.036, .42/max(1, len(others)))
    for index, run in enumerate(others):
        code = int(settings[run]['RF'])
        a, w = statistics[str(run)]['amplitude'], statistics[str(run)]['fwhm']
        nfailed = sum(not finite(r['fwhm']) for r in rows[run])
        nnarrow = sum(finite(r['fwhm']) and 2 <= r['fwhm'] <= 11 for r in rows[run])
        values = [str(code), '%.2f' % (80./code), str(run), str(a['n']), _format(a['pearson']), _format(a['spearman']),
                  str(w['n']), _format(w['pearson']), _format(w['spearman']), str(nfailed), str(nnarrow)]
        y = .805-index*spacing
        for x, value in zip(xs, values):
            _text(ROOT, keep, x, y, value, .021, align=22)
    ref = rows[REFERENCE_RUN]
    finite_n = sum(finite(r['fwhm']) for r in ref)
    right_n = sum(r['status'] == 6 for r in ref)
    both_n = sum(r['status'] == 7 for r in ref)
    _text(ROOT, keep, .035, .335,
          'RF1/run300: widths %d/%d; missing right crossings %d; missing both %d.' % (finite_n, len(ref), right_n, both_n), .023)
    rf2 = 'RF2/run302 included from supplied saved measurements.' if 302 in runs else 'RF2/run302 was not supplied; no point or measurement is fabricated.'
    _text(ROOT, keep, .035, .295, rf2, .021)
    _text(ROOT, keep, .035, .246, 'Geometry provenance: production sumV2 mapping SHA256 0d94c8501221...19477e; cell-ID encoding verified against Setup.cc.', .020)
    _text(ROOT, keep, .035, .211, 'Nominal modules 2 and 3 map to ASIC indices 1 and 5. Matching configuration hashes do not verify installed hardware.', .020)
    _text(ROOT, keep, .035, .176, 'Earlier transfer ROOT files were reused; their embedded Setup mapping has not been independently verified here.', .020)
    _text(ROOT, keep, .035, .141, 'Correlations and narrow-width labels are descriptive. They do not establish coupling, a hardware cause or physical validity.', .020)
    _text(ROOT, keep, .035, .106, 'Native ROOT file preserves all finite graphs, metric maps, status maps, finite masks and numerical correlation matrices.', .020)
    for metric in METRICS:
        h = ROOT.TH2D('same_channel_statistics_'+metric, 'RF1 finite pairs;Statistic;Comparison', 3, .5, 3.5, max(1, len(others)), .5, max(1, len(others))+.5)
        h.SetDirectory(0)
        for i, label in enumerate(('n', 'Pearson r', 'Spearman rho'), 1):
            h.GetXaxis().SetBinLabel(i, label)
        for j, run in enumerate(others, 1):
            h.GetYaxis().SetBinLabel(j, 'RF%d run%d' % (int(settings[run]['RF']), run))
            s = statistics[str(run)][metric]
            for i, key in enumerate(('n', 'pearson', 'spearman'), 1):
                h.SetBinContent(i, j, float(s[key]) if s[key] is not None else float('nan'))
        keep.append(h)
        _write(root, h)
    return c


def draw(ROOT, rows, settings, out, mapping_path, groups=None):
    """Export native ROOT/PDF/PNGs and return numerical/provenance metadata.

    `rows`: run -> [{cell, status, amplitude, fwhm, peak_time}, ...]
    `settings`: run -> run-DB row (RF/CF/CC/CFComp may be strings).
    `groups`: optional mapping or iterable of (parameter, [runs]).
    """
    out = Path(out)
    runs = select_rf_runs(rows, settings, groups)
    cells = set(index_rows(rows[REFERENCE_RUN]))
    if not cells:
        raise ValueError('No selected RF channels')
    for run in runs:
        indexed = index_rows(rows[run])
        if set(indexed) != cells:
            raise ValueError('RF runs do not have identical channel-ID sets')
        for row in rows[run]:
            if row['status'] != int(row['status']) or int(row['status']) not in STATUS_LABELS:
                raise ValueError('Unknown/noninteger extraction status')
            if finite(row['fwhm']) and (row['status'] != 0 or row['fwhm'] <= 0):
                raise ValueError('Finite width inconsistent with saved extraction status')
    geometry = load_geometry(mapping_path, cells)
    stats = {str(run): {metric: pair_statistics(rows[REFERENCE_RUN], rows[run], metric) for metric in METRICS}
             for run in runs if run != REFERENCE_RUN}
    metadata = {'reference_run': REFERENCE_RUN, 'rf_runs': runs, 'cell_count': len(cells),
                'mapping_sha256': VERIFIED_MAPPING_SHA256,
                'mapping_path': str(Path(mapping_path).resolve()),
                'geometry_status': 'configuration-derived nominal geometry, installed hardware and transfer-ROOT map unverified',
                'resistance_status': 'provisional H2GCROC3B R=80/code kOhm; installed ASIC revision unverified',
                'correlations': stats, 'geometry': geometry}
    out.mkdir(parents=True, exist_ok=True)
    root_path = out/'HGCROC_RFChannels.root'
    pdf_path = out/'HGCROC_RFChannels.pdf'
    root = ROOT.TFile(str(root_path), 'RECREATE')
    if not root or root.IsZombie():
        raise OSError('Cannot create ROOT diagnostics file')
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    ROOT.gStyle.SetOptTitle(0)
    ROOT.gStyle.SetPaperSize(27., 18.)
    ROOT.gStyle.SetPalette(ROOT.kViridis)
    keep, canvases = [], []
    try:
        # Save every supplied finite metric, not only the representative map runs.
        for run in runs:
            status = ROOT.TH1I('status_run%d' % run, 'Stored extraction status;Cell ID;Status enum', len(cells), .5, len(cells)+.5)
            status.SetDirectory(0)
            for i, row in enumerate(sorted(rows[run], key=lambda r:r['cell']), 1):
                status.GetXaxis().SetBinLabel(i, str(row['cell']))
                status.SetBinContent(i, row['status'])
            keep.append(status)
            _write(root, status)
            for metric in METRICS:
                g = ROOT.TGraph()
                g.SetName('values_run%d_%s' % (run, metric))
                g.SetTitle('Unfiltered finite saved measurements;Cell ID;%s' % metric)
                for row in sorted(rows[run], key=lambda r:r['cell']):
                    if finite(row[metric]):
                        g.SetPoint(g.GetN(), row['cell'], row[metric])
                keep.append(g)
                _write(root, g)
        map_runs = [REFERENCE_RUN] + [r for r in COMPARISON_RUNS if r in runs]
        for metric in ('amplitude', 'fwhm', 'status'):
            canvases.append(_map_page(ROOT, rows, settings, geometry, map_runs, metric, root, keep, len(canvases)+1))
        comparisons = [r for r in COMPARISON_RUNS if r in runs]
        if comparisons:
            canvases.append(_scatter_page(ROOT, rows, settings, geometry, comparisons, stats, root, keep, len(canvases)+1))
        canvases.append(_summary_page(ROOT, rows, settings, runs, stats, root, keep, len(canvases)+1))
        metadata['page_count'] = len(canvases)
        info = ROOT.TObjString(json.dumps(metadata, sort_keys=True))
        keep.append(info)
        root.cd()
        info.Write('rf_channel_metadata_json')
        canvases[0].Print(str(pdf_path)+'[')
        try:
            for number, canvas in enumerate(canvases, 1):
                canvas.cd()
                canvas.Modified()
                canvas.Update()
                _write(root, canvas)
                canvas.Print(str(pdf_path))
                canvas.SaveAs(str(out/('HGCROC_RFChannels_%02d.png' % number)))
        finally:
            canvases[-1].Print(str(pdf_path)+']')
    finally:
        root.Close()
        for canvas in canvases:
            canvas.Close()
    (out/'HGCROC_RFChannels.json').write_text(json.dumps(metadata, indent=2, sort_keys=True)+'\n')
    return metadata
