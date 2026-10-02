#!/usr/bin/env python3
"""Review late refinement jumps at BNL using saved histograms and fit parameters.

Requires PyROOT and plot_discrepant_spectra.py beside this script. No refitting.
Default: 10 cells, 40 pages, three stages per page; original and valley boundaries.
"""
import argparse
from array import array
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import sys
import zipfile

import plot_discrepant_spectra as spectra

CASES = {
    'b2': {
        704: 'New Adaptive R8: H -24.4%, Gaussian width nearly vanishes',
        579: 'New Adaptive R8: H +2.68%',
        2562: 'New Adaptive R8: H -1.33%',
        709: 'New Adaptive R8: H +1.22%',
        2118: 'New Legacy R8: H +1.20%; check Adaptive missing fits',
        1287: 'Old Legacy R8: H +55.0%; compare improvement with new boundary',
    },
    'e1': {
        196: 'New Legacy R5: H -2.02%',
        1348: 'New Legacy R5: H -1.71%',
    },
    'b1': {
        704: 'Stable final-step comparison at the same detector cell as B2 704',
        1287: 'Stable final-step comparison at the same detector cell as B2 1287',
    },
}
BOUNDARIES = ('original', 'valley')
MODELS = spectra.MODELS
load = lambda p: json.loads(p.read_text())


def truth(v):
    return str(v).lower() in ('true', '1')


def checked_rows(path, dataset, model, stage):
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    result = {}
    for r in rows:
        cell = int(r['cell_id'])
        if cell in result:
            raise ValueError('Duplicate cell in ' + str(path))
        for key, expected in (('dataset', dataset), ('model', model), ('stage', stage)):
            if r.get(key) != expected:
                raise ValueError('Wrong report identity: ' + str(path))
        result[cell] = r
    return result


def collect(root, datasets):
    """Resolve originals from frozen provenance, not assumed campaign names."""
    manifest = load(root/'manifest.json')
    references = {x['copy']: x for x in manifest['reference_files']}
    records, inputs = {}, {}
    for dataset in datasets:
        final = 8 if dataset == 'b2' else 5
        for boundary in BOUNDARIES:
            for model in MODELS:
                for stage in ['mip'] + [f'refine{n}' for n in range(1, final+1)]:
                    relative = Path(model)/dataset/stage/'cells.csv'
                    if boundary == 'original':
                        info = references[str(Path('references')/relative)]
                        path = root/info['copy']
                        if spectra.sha(path) != info['sha256']:
                            raise ValueError('Frozen reference changed: ' + str(path))
                        folder = Path(info['original']).parent
                    else:
                        path = root/relative
                        folder = path.parent
                    rows = checked_rows(path, dataset, model, stage)
                    inputs[str(path)] = spectra.sha(path)
                    for cell in CASES[dataset]:
                        if cell not in rows:
                            raise ValueError(f'Missing {dataset} {model} {stage} cell {cell}')
                        records[dataset, boundary, model, stage, cell] = dict(
                            row=rows[cell], folder=folder, report=path)
    return manifest, records, inputs


def write_history(path, records):
    rows = []
    for (dataset, boundary, model, stage, cell), record in records.items():
        r = record['row']
        row = dict(dataset=dataset, boundary=boundary, model=model,
                   cell_id=cell, stage=stage, fit_saved=truth(r['fit_saved']))
        for key in ('scale_h', 'mpv', 'landau_width', 'gaussian_sigma', 'area',
                    'fit_xmin', 'fit_xmax', 'entries', 'chi2_ndf', 'range_status',
                    'range_usable', 'range_old', 'range_new', 'range_peak',
                    'range_valley', 'range_fraction', 'histogram_sha256'):
            row[key] = r.get(key, '')
        n = int(stage[6:]) if stage.startswith('refine') else 0
        prior = records.get((dataset, boundary, model,
                             'mip' if n == 1 else f'refine{n-1}', cell))
        valid = row['fit_saved'] and prior and truth(prior['row']['fit_saved'])
        for key in ('scale_h', 'mpv', 'landau_width', 'gaussian_sigma', 'fit_xmin'):
            before = spectra.number(prior['row'].get(key)) if prior else None
            after = spectra.number(r.get(key))
            change = after-before if valid and before is not None and after is not None else None
            row['step_'+key] = change
            row['step_fraction_'+key] = change/abs(before) if change is not None and before else None
        row['report'] = str(record['report'])
        rows.append(row)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def verify_channel(data, row):
    """Check saved TF1 parameters/range and the original-bin count fingerprint."""
    if bool(data['fit']) != truth(row['fit_saved']):
        raise ValueError('CSV/ROOT saved-fit mismatch')
    h = data['hist']
    if bool(h) != truth(row['histogram_present']):
        raise ValueError('CSV/ROOT histogram-presence mismatch')
    if h:
        counts = [float(h.GetBinContent(i)) for i in range(h.GetNbinsX()+2)]
        if not all(math.isfinite(x) and x >= 0 for x in counts):
            raise ValueError('Nonfinite or negative histogram content')
        fingerprint = dict(counts=counts, nbins=h.GetNbinsX(),
                           xmin=h.GetXaxis().GetXmin(), xmax=h.GetXaxis().GetXmax())
        digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
        if digest != row['histogram_sha256']:
            raise ValueError('CSV/ROOT original-bin histogram fingerprint mismatch')
        data['histogram_sha256'] = digest
    if data['fit']:
        values = dict(zip(('landau_width', 'mpv', 'area', 'gaussian_sigma'), data['parameters']))
        values.update(fit_xmin=data['xmin'], fit_xmax=data['xmax'])
        for key, actual in values.items():
            expected = spectra.number(row.get(key))
            if expected is None or not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError('CSV/ROOT mismatch: ' + key)
        expected = spectra.number(row.get('range_new'))
        if expected is not None and not math.isclose(data['xmin'], expected, abs_tol=1e-9):
            raise ValueError('Saved TF1 lower edge differs from range audit')


def histogram_graph(ROOT, data):
    """Display finite stored errors; never invent errors for NaN Sumw2 bins."""
    h = data['hist']
    data['bad_error_bins'] = 0
    if not h:
        return
    x, y, errors = array('d'), array('d'), array('d')
    for i in range(1, h.GetNbinsX()+1):
        x.append(h.GetBinCenter(i)); y.append(h.GetBinContent(i))
        error = float(h.GetBinError(i))
        bad = not math.isfinite(error) or error < 0
        data['bad_error_bins'] += int(bad)
        errors.append(0. if bad else error)
    g = ROOT.TGraphErrors(len(x), x, y, array('d', [0.]*len(x)), errors)
    g.SetMarkerStyle(20); g.SetMarkerSize(.45); g.SetLineColor(ROOT.kBlack)
    data.update(points=g, point_x=x, point_y=y, point_error=errors)


def limits(data):
    fits = [d for d in data.values() if d.get('fit')]
    if not fits:
        raise ValueError('No saved fit in any panel for this cell')
    lo, hi = min(d['xmin'] for d in fits), max(d['xmax'] for d in fits)
    left, right = max(0., lo-.08*(hi-lo)), hi+.03*(hi-lo)
    maximum = 0.
    for d in data.values():
        values = [y+e for x, y, e in zip(d.get('point_x', []), d.get('point_y', []),
                                        d.get('point_error', [])) if left <= x <= right]
        values += [y for x, y in zip(d.get('curve_x', []), d.get('curve_y', [])) if left <= x <= right]
        maximum = max(maximum, max(values, default=0.))
    return left, right, max(1., maximum)*1.12


def fmt(v):
    n = spectra.number(v)
    return '?' if n is None else f'{n:.5g}'


def draw(ROOT, dataset, cell, boundary, model, stages, data, axes, png, pdf):
    canvas = ROOT.TCanvas('boundary_case', 'Saved-fit history', 1800, 700)
    canvas.SetCanvasSize(1800, 700)
    canvas.Divide(3, 1, .005, .005)
    keep = []
    left, right, maximum = axes
    for col, stage in enumerate(stages, 1):
        d = data[boundary, model, stage]; r = d['row']
        pad = canvas.cd(col)
        pad.SetLeftMargin(.13); pad.SetBottomMargin(.13); pad.SetTopMargin(.34)
        frame = pad.DrawFrame(left, 0., right, maximum)
        frame.SetTitle(f'{dataset.upper()} cell {cell} | {boundary} {model} | {stage};ADC;Counts / original bin')
        keep.append(frame)
        if d.get('points'):
            d['points'].Draw('PZ SAME')
        if d.get('graph'):
            d['graph'].Draw('L SAME')
        for edge in (d.get('xmin'), d.get('xmax')):
            if edge is not None:
                line = ROOT.TLine(edge, 0., edge, maximum)
                line.SetLineStyle(3); line.SetLineColor(ROOT.kGray+2); line.Draw(); keep.append(line)
        lines = [f'H={fmt(r.get("scale_h"))}   MPV={fmt(r.get("mpv"))}',
                 f'wL={fmt(r.get("landau_width"))}   #sigma={fmt(r.get("gaussian_sigma"))}',
                 f'fit range [{fmt(r.get("fit_xmin"))}, {fmt(r.get("fit_xmax"))}]',
                 ('boundary: '+r.get('range_status', 'original rule')),
                 f'entries={fmt(r.get("entries"))}   #chi^{{2}}/ndf={fmt(r.get("chi2_ndf"))}']
        if not d['fit']:
            lines[1] = 'NO SAVED FIT; H may be carried forward'
        if not d['hist']:
            lines[3] = 'NO SAVED HISTOGRAM'
        if d.get('error'):
            lines[3] = 'CURVE ERROR: see index.html'
        if d['bad_error_bins']:
            lines.append(f'{d["bad_error_bins"]} nonfinite errors omitted; counts unchanged')
        for i, text in enumerate(lines):
            keep.append(spectra.label(ROOT, text, x=.13, y=.93-i*.044, size=.031))
    canvas.Modified(); canvas.Update()
    canvas.Print(str(png)); canvas.Print(str(pdf)); canvas.Close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--datasets', nargs='+', choices=tuple(CASES), default=list(CASES))
    p.add_argument('--max-points', type=int, default=1000000)
    a = p.parse_args(); a.root = a.root.resolve(); a.out = a.out.resolve()
    if a.max_points < 2001:
        p.error('--max-points must be >= 2001')
    archive = Path(str(a.out)+'.zip')
    if (a.out.exists() and any(a.out.iterdir())) or archive.exists():
        p.error('Use an empty output directory and a new ZIP name; preserving existing review')
    print('Checking frozen references and complete parameter histories...', flush=True)
    manifest, records, inputs = collect(a.root, a.datasets)
    # Preflight all histogram files before starting ROOT or creating output.
    paths = {}
    for dataset in a.datasets:
        final = 8 if dataset == 'b2' else 5
        for boundary in BOUNDARIES:
            for model in MODELS:
                for n in range(final-2, final+1):
                    stage = f'refine{n}'
                    record = records[dataset, boundary, model, stage, next(iter(CASES[dataset]))]
                    matches = list(record['folder'].glob('*_Hists.root'))
                    if len(matches) != 1:
                        raise ValueError('Expected one histogram file in '+str(record['folder']))
                    paths[dataset, boundary, model, stage] = matches[0]
    import ROOT
    ROOT.gROOT.SetBatch(True); ROOT.gStyle.SetOptStat(0); ROOT.gStyle.SetOptTitle(1)
    if ROOT.gROOT.GetVersion() != manifest['reference_root_version']:
        raise ValueError('Use original ROOT '+manifest['reference_root_version']+'; current '+ROOT.gROOT.GetVersion())
    header_hash, source_info, namespaces = None, {}, {}
    for boundary, parent in (('original', Path(manifest['source_parent'])), ('valley', a.root)):
        namespaces[boundary] = 'boundary_cases_'+boundary
        header_hash, source_info[boundary] = spectra.declare_evaluators(
            ROOT, parent, namespaces[boundary], header_hash)
    a.out.mkdir(parents=True, exist_ok=True)
    write_history(a.out/'parameter-history.csv', records)
    metadata = dict(refit=False, cases={d: CASES[d] for d in a.datasets},
                    root_version=ROOT.gROOT.GetVersion(), sources=source_info,
                    manifest_sha256=spectra.sha(a.root/'manifest.json'), reports=inputs,
                    scripts={Path(__file__).name: spectra.sha(Path(__file__)),
                             'plot_discrepant_spectra.py': spectra.sha(Path(spectra.__file__))},
                    histogram_files={str(path): dict(size=path.stat().st_size,
                                     mtime_ns=path.stat().st_mtime_ns) for path in paths.values()},
                    error_display='Original counts and finite stored errors; nonfinite errors omitted, never replaced by Poisson errors. Original ROOT objects preserved in histograms.root.',
                    panels=[], errors=[])
    gallery = ['<!doctype html><meta charset="utf-8"><title>Late refinement cases</title>',
               '<style>body{font:16px sans-serif;margin:2em}img{max-width:100%}section{margin:3em 0}</style>',
               '<h1>Late refinement cases</h1><p>Original bins and saved fits; no refitting. '
               'Three stages per page; all four pages for a cell share axes. Dotted lines are saved fit limits. '
               'Each stage and method has its own selected histogram. Missing fits have no curve. '
               'Nonfinite stored errors are omitted from display, with counts unchanged.</p>',
               '<p><a href="parameter-history.csv">Complete parameter and lower-boundary histories</a> | '
               '<a href="histograms.root">Unmodified selected ROOT histograms and saved fits</a> | '
               '<a href="manifest.json">Provenance</a></p>']
    packed = ROOT.TFile(str(a.out/'histograms.root'), 'RECREATE')
    if not packed or packed.IsZombie():
        raise ValueError('Cannot create histogram bundle')
    try:
        for dataset in a.datasets:
            final = 8 if dataset == 'b2' else 5
            stages = [f'refine{n}' for n in range(final-2, final+1)]
            files = {}
            pdf = a.out/f'{dataset}-cases.pdf'
            # ROOT initializes PDF geometry from this canvas, even with '['.
            # A 10x10 window can have a zero drawable size after decorations.
            book = ROOT.TCanvas('book', 'book', 1800, 700)
            book.SetCanvasSize(1800, 700)
            book.Print(str(pdf)+'[')
            try:
                for key, path in paths.items():
                    if key[0] != dataset:
                        continue
                    f = ROOT.TFile.Open(str(path), 'READ')
                    if not f or f.IsZombie() or f.TestBit(ROOT.TFile.kRecovered):
                        raise ValueError('Invalid ROOT file: '+str(path))
                    files[key[1:]] = f
                gallery.append(f'<h2>{dataset.upper()}</h2><p><a href="{pdf.name}">PDF book</a></p>')
                for cell, reason in CASES[dataset].items():
                    print(f'{dataset.upper()} cell {cell}: {reason}', flush=True)
                    data = {}
                    for boundary in BOUNDARIES:
                        for model in MODELS:
                            for stage in stages:
                                key = (boundary, model, stage)
                                print(f'  {boundary} {model} {stage}', flush=True)
                                d = spectra.read_channel(ROOT, files[key], cell)
                                d['row'] = records[dataset, boundary, model, stage, cell]['row']
                                verify_channel(d, d['row'])
                                histogram_graph(ROOT, d)
                                if d['fit']:
                                    try:
                                        spectra.curve(ROOT, namespaces[boundary], model, d, a.max_points)
                                    except Exception as exc:
                                        d['error'] = str(exc)
                                        metadata['errors'].append(f'{dataset} {cell} {boundary} {model} {stage}: {exc}')
                                # Preserve the original objects, including NaN error storage.
                                packed.cd()
                                folder = packed
                                for part in (dataset, boundary, model, stage, 'cell'+str(cell)):
                                    folder = folder.GetDirectory(part) or folder.mkdir(part)
                                folder.cd()
                                if d['hist']: d['hist'].Write('histogram')
                                if d['fit']: d['fit'].Write('saved_fit')
                                info = dict(dataset=dataset, cell_id=cell, boundary=boundary, model=model, stage=stage)
                                info.update({k: d[k] for k in ('parameters', 'xmin', 'xmax', 'samples', 'sample_step',
                                                              'bad_error_bins', 'histogram_sha256', 'error') if k in d})
                                metadata['panels'].append(info); data[key] = d
                    axes = limits(data)
                    gallery.append(f'<section><h3>{dataset.upper()} cell {cell}</h3><p>{html.escape(reason)}</p>')
                    for boundary in BOUNDARIES:
                        for model in MODELS:
                            name = f'{dataset}-cell{cell}-{boundary}-{model}.png'
                            draw(ROOT, dataset, cell, boundary, model, stages, data, axes, a.out/name, pdf)
                            gallery.append(f'<h4>{boundary} {model}</h4><img loading="lazy" src="{name}">')
                    gallery.append('</section>')
                    (a.out/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
                    (a.out/'index.html').write_text('\n'.join(gallery))
            finally:
                book.Print(str(pdf)+']'); book.Close()
                for f in files.values(): f.Close()
    finally:
        packed.Close()
    gallery.extend('<p><strong>'+html.escape(error)+'</strong></p>' for error in metadata['errors'])
    (a.out/'index.html').write_text('\n'.join(gallery))
    (a.out/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(a.out.iterdir()): z.write(path, a.out.name+'/'+path.name)
    print('Review:', a.out/'index.html', flush=True)
    print('Download:', archive, flush=True)
    if metadata['errors']:
        print(f'{len(metadata["errors"])} curve errors explicitly marked; see index.html.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
