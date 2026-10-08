#!/usr/bin/env python3
"""Package existing PS-2026 calibration PNGs; never run fits or touch inputs."""
import argparse
import csv
import html
import json
import re
import shutil
import textwrap
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

CATALOG = {
    "ps-a1": {
        "muon_runs": [
            86,
            87,
            88,
            89,
            90,
            91,
            92
        ],
        "pedestal_runs": [
            85
        ],
        "notes": [
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred"
    },
    "ps-a2": {
        "muon_runs": [
            121,
            122,
            123,
            124,
            125,
            126
        ],
        "pedestal_runs": [
            120
        ],
        "notes": [
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred"
    },
    "ps-b1": {
        "muon_runs": [
            189,
            190,
            191,
            192,
            193
        ],
        "pedestal_runs": [
            215
        ],
        "notes": [
            "Run 191 is present in the merge list but absent from the active conversion list.",
            "Pedestal dead time is 2000; muons include 1700, 1800 and 2000.",
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred"
    },
    "ps-b2": {
        "muon_runs": [
            217,
            218,
            219,
            220
        ],
        "pedestal_runs": [
            215
        ],
        "notes": [
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred"
    },
    "ps-c1": {
        "muon_runs": [
            131,
            132,
            133,
            134,
            135,
            136
        ],
        "pedestal_runs": [
            130
        ],
        "notes": [
            "Pedestal dead time is 4000; muons include 4000 and 2000."
        ],
        "pedestal_evidence": "script-assigned"
    },
    "ps-c2": {
        "muon_runs": [
            177,
            179,
            178,
            181,
            182,
            180,
            183,
            184
        ],
        "pedestal_runs": [
            171
        ],
        "notes": [
            "Pedestal dead time is 2000; muons use 1500."
        ],
        "pedestal_evidence": "script-assigned"
    },
    "ps-d1": {
        "muon_runs": [
            242,
            241,
            240,
            244
        ],
        "pedestal_runs": [
            238
        ],
        "notes": [
            "Pedestal 238 records CC=3; muons record CC=5. Also fetch 265 (CC=5) for review; no replacement is selected."
        ],
        "pedestal_evidence": "script-assigned; CC mismatch"
    },
    "ps-d2": {
        "muon_runs": [
            266,
            267,
            268,
            269
        ],
        "pedestal_runs": [
            265
        ],
        "notes": [],
        "pedestal_evidence": "script-assigned"
    },
    "ps-e1": {
        "muon_runs": [
            288,
            289,
            290,
            291
        ],
        "pedestal_runs": [
            287
        ],
        "notes": [],
        "pedestal_evidence": "script-assigned"
    },
    "ps-e2": {
        "muon_runs": [
            316,
            317,
            318,
            319,
            320
        ],
        "pedestal_runs": [
            315
        ],
        "notes": [],
        "pedestal_evidence": "script-assigned"
    },
    "ps-f1": {
        "muon_runs": [
            339,
            340,
            341,
            342,
            343,
            344
        ],
        "pedestal_runs": [
            338
        ],
        "notes": [
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred"
    },
    "ps-f2": {
        "muon_runs": [
            367,
            368,
            369,
            370
        ],
        "pedestal_runs": [
            366
        ],
        "notes": [
            "Muon runs 367-370 are labelled Muon- beam shutter open.",
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred"
    },
    "ps-g1": {
        "muon_runs": [
            380,
            381,
            382,
            383
        ],
        "pedestal_runs": [
            379
        ],
        "notes": [
            "Pedestal 379 records CC=15; muons record CC=9. Also fetch 404 (CC=9) for review; no replacement is selected.",
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred; CC mismatch"
    },
    "ps-g2": {
        "muon_runs": [
            405,
            406,
            407,
            408
        ],
        "pedestal_runs": [
            404
        ],
        "notes": [
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred"
    },
    "ps-h1": {
        "muon_runs": [
            427,
            428,
            429,
            430
        ],
        "pedestal_runs": [
            425
        ],
        "notes": [
            "The FullSetH branch emits a G1 filename. Its board comment says V1 while its conversion uses V2.",
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred; merge name needs correction"
    },
    "ps-i1": {
        "muon_runs": [
            427,
            428,
            429,
            430
        ],
        "pedestal_runs": [
            425
        ],
        "notes": [
            "The PartSetI branch repeats its first merge twice. Its board comment says V1 while its conversion uses V2.",
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred; same muons as H1"
    },
    "ps-i2": {
        "muon_runs": [
            464,
            463
        ],
        "pedestal_runs": [
            462
        ],
        "notes": [
            "Runs 463/464 are listed as the second muon set in comments; an active I2 merge is missing.",
            "The board comment says V1 while the conversion uses V2.",
            "pedestal association inferred"
        ],
        "pedestal_evidence": "inferred; only listed in recipe comments"
    }
}
STAGES = ['pedestal', 'transfer', 'mip'] + ['refine%d' % n for n in range(1, 6)]
METHODS = {
    'legacy': 'Legacy HG fitting; original fit boundary',
    'adaptive': 'Adaptive HG fitting; original fit boundary',
}
# Page order transcribed from F. Bock's 27-page SummarySetB.pdf.
# R5 names have no _2nd suffix (that suffix belongs to the initial MIP stage).
SUMMARY_PAGES = [
    ('HG_FWHMMip.png', 'HG FWHM'),
    ('HG_GaussSigMip.png', 'HG Gaussian width'),
    ('HG_LandMPVMip.png', 'HG Landau MPV'),
    ('HG_LandSigMip.png', 'HG Landau width'),
    ('HG_MaxMip.png', 'HG peak position'),
    ('HGscaleChi2VsLayer.png', 'HG chi-square / ndf'),
] + [
    ('MIP_HG_Layer%02d.png' % layer, 'MIP spectra and fits - layer %d' % layer)
    for layer in range(8)
] + [
    ('MipTriggXY.png', 'Trigger counts in XY'),
    ('MuonTriggers.png', 'Trigger counts by channel'),
    ('SNRTriggVsLayer.png', 'Signal-to-noise ratio'),
    ('SuppressionNoise.png', 'S/B in noise region'),
    ('SuppressionSignal.png', 'S/B in signal region'),
] + [
    ('TriggPrimitive_Layer%02d.png' % layer, 'Trigger primitives - layer %d' % layer)
    for layer in range(8)
]
CSS = '''body{font:17px system-ui,sans-serif;max-width:1500px;margin:30px auto;padding:0 24px;color:#182839}
a{color:#12618b}table{border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #ccd;text-align:left}
figure{margin:24px 0;border-top:1px solid #ccd;padding-top:16px}img{max-width:100%;height:auto}
figcaption{overflow-wrap:anywhere}nav{line-height:2}details{margin:20px 0}small{color:#536273}'''


def natural(p):
    return [int(v) if v.isdigit() else v.lower() for v in re.split(r'(\d+)', str(p))]


def page(title, body):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>%s</title><style>%s</style><body><h1>%s</h1>%s</body></html>' % (html.escape(title), CSS, html.escape(title), body)


def figure(rel, caption):
    url = quote(rel.as_posix())
    return '<figure><figcaption>%s</figcaption><a href="%s"><img loading="lazy" src="%s" alt="%s"></a></figure>' % (html.escape(caption), url, url, html.escape(caption))


def select_summary(paths):
    """Resolve exact R5 basenames; never substitute another stage or duplicate."""
    by_name = {}
    for p in paths:
        by_name.setdefault(p.name, []).append(p)
    pages = []
    for name, title in SUMMARY_PAGES:
        matches = by_name.get(name, [])
        if len(matches) > 1:
            raise ValueError('Ambiguous R5 plot %s: %s' % (name, ', '.join(map(str, matches))))
        # ROOT omits layer panels when all its channels are masked. Keep a clearly
        # marked missing page so later pages retain the reference numbering.
        if not matches and '_Layer' not in name:
            raise ValueError('Missing R5 summary map: ' + name)
        pages.append((matches[0] if matches else None, title, name))
    return pages


def summary_pdf_name(key):
    return 'SummaryPS_' + key[3:].upper() + '.pdf'


def pdf_report(path, groups, method):
    """One plot per page, with no added cover/title pages or plot overlays."""
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader
    c = Canvas(str(path), pagesize=(567, 499))
    c.setTitle('PS April 2026 - R5 summary - ' + method + ' - ' + ', '.join(k.upper() for k in groups))
    c.setAuthor('Paul Nord')
    c.setSubject(method + '; page order follows F. Bock SummarySetB')
    for key, paths in groups.items():
        for number, (p, title, name) in enumerate(paths, 1):
            # Keep the original image aspect and every pixel; no resampling.
            if p is not None:
                im = ImageReader(str(p)); w, h = im.getSize()
                width, height = 567, 567 * h / w
            else:
                width, height = 567, 421
            c.setPageSize((width, height))
            bookmark = '%s-%02d' % (key, number)
            c.bookmarkPage(bookmark)
            if number == 1:
                set_bookmark = key + '-r5'
                c.bookmarkPage(set_bookmark)
                c.addOutlineEntry(key.upper() + ' - R5 - ' + method, set_bookmark, 0)
            c.addOutlineEntry('%02d - %s' % (number, title), bookmark, 1)
            if p is not None:
                c.drawImage(im, 0, 0, width=width, height=height, mask='auto')
            else:
                c.setFont('Helvetica-Bold', 18)
                c.drawString(32, height-60, key.upper() + ' - R5 plot unavailable')
                c.setFont('Helvetica', 12)
                y = height-100
                for line in [title, 'Expected file: ' + name,
                             'No matching R5 PNG was found. No other stage was substituted.',
                             'ROOT can omit panels for masked layers; the reason has not been verified.']:
                    for part in textwrap.wrap(line, 75):
                        c.drawString(32, y, part); y -= 18
                    y -= 10
            c.showPage()
    c.save()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', required=True, type=Path, help='CALWORK with ps-a1 ... ps-i2')
    ap.add_argument('--out', required=True, type=Path, help='New report directory')
    ap.add_argument('--method', required=True, choices=sorted(METHODS),
                    help='HG fitter used for these results (original boundary); labels only, no refitting')
    ap.add_argument('--pdf', action='store_true', help='Make 27-page per-set summaries and a combined PDF (requires reportlab)')
    ap.add_argument('--sets', nargs='+', choices=sorted(CATALOG), default=sorted(CATALOG))
    args = ap.parse_args()
    method = METHODS[args.method]
    args.sets = list(dict.fromkeys(args.sets))
    if args.pdf:
        try:
            import reportlab  # noqa: F401
        except ImportError:
            ap.error('--pdf needs reportlab: python3 -m pip install --user reportlab')
    root, out = args.root.resolve(), args.out.resolve()
    if out.exists() or out.with_suffix('.zip').exists():
        ap.error('Output or ZIP already exists; choose a new --out directory.')
    inventory, summaries, problems = {}, {}, []
    for key in args.sets:
        stages = {}
        for stage in STAGES:
            stages[stage] = sorted((root/key/'plots'/stage).rglob('*.png'), key=natural)
        if not stages['refine5']:
            problems.append(key + ': no R5 PNGs')
        try:
            summaries[key] = select_summary(stages['refine5'])
        except ValueError as e:
            problems.append(key + ': ' + str(e))
        final = list((root/key/'final').glob('*_calib.txt'))
        if not final or not all(p.stat().st_size for p in final):
            problems.append(key + ': missing/empty final calibration text')
        for paths in stages.values():
            for p in paths:
                with p.open('rb') as f:
                    if f.read(8) != b'\x89PNG\r\n\x1a\n':
                        problems.append('Invalid PNG header: ' + str(p))
        inventory[key] = stages
    if problems:
        ap.error('\n'.join(problems))
    out.mkdir(parents=True)
    stamp = datetime.now(timezone.utc).isoformat()
    manifest = {'created_utc': stamp, 'source_root': str(root), 'method': method,
                'method_key': args.method,
                'summary_template': 'F. Bock SummarySetB: 27 pages, layers 0-7',
                'recipe_metadata': {k: CATALOG[k] for k in args.sets},
                'plots': [], 'summary_pages': [], 'warnings': []}
    rows, pdf_groups = [], {}
    for key, stages in inventory.items():
        print('Packaging ' + key, flush=True)
        m = CATALOG[key]
        intro = '<p><a href="index.html">All sets</a></p><p>%s</p>' % method
        if args.pdf:
            intro += '<p><a href="%s">27-page R5 summary PDF</a></p>' % summary_pdf_name(key)
        intro += '<p>Muon runs: %s<br>Pedestal runs: %s<br>Pedestal association: %s</p>' % (
            ', '.join(map(str,m['muon_runs'])), ', '.join(map(str,m['pedestal_runs'])), html.escape(m['pedestal_evidence']))
        intro += '<h2>Recipe notes</h2><ul>' + ''.join('<li>%s</li>' % html.escape(n) for n in m['notes']) + '</ul>'
        intro += '<p>These notes describe the source recipe, not findings from this report.</p>'
        links = []
        for stage, paths in stages.items():
            figs = []
            for p in paths:
                rel = p.relative_to(root)
                dest = out/rel; dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
                label = p.relative_to(root/key/'plots'/stage).as_posix()
                figs.append(figure(rel, label))
                manifest['plots'].append({'set':key, 'stage':stage, 'path':rel.as_posix(), 'bytes':dest.stat().st_size})
            stage_name = key + '-' + stage + '.html'
            (out/stage_name).write_text(page(key.upper()+' - '+stage, '<p><a href="%s.html">Back to set</a></p>' % key + (''.join(figs) or '<p>No plots found for this stage.</p>')), encoding='utf-8')
            links.append('<li><a href="%s">%s (%d plots)</a></li>' % (stage_name,stage,len(paths)))
        selected_figures, pdf_groups[key] = [], []
        for number, (p, title, name) in enumerate(summaries[key], 1):
            rel = p.relative_to(root) if p else None
            manifest['summary_pages'].append({'set': key, 'page': number, 'title': title,
                                              'expected_file': name,
                                              'path': rel.as_posix() if rel else '',
                                              'status': 'present' if p else 'missing'})
            if p:
                selected_figures.append(figure(rel, '%02d - %s' % (number, title)))
            else:
                warning = '%s: missing R5 panel %s; placeholder at page %d' % (key, name, number)
                print('WARNING: ' + warning, flush=True)
                manifest['warnings'].append(warning)
                selected_figures.append('<p><strong>%02d - %s: plot unavailable (%s)</strong></p>' % (number, html.escape(title), name))
            pdf_groups[key].append((out/rel if rel else None, title, name))
        body = intro + '<h2>All stages (complete PNG collection)</h2><ul>' + ''.join(links) + '</ul><h2>R5 summary in Fredi\'s page order</h2>' + ''.join(selected_figures)
        (out/(key+'.html')).write_text(page(key.upper(),body), encoding='utf-8')
        # Text constants are small and useful alongside the report. Event trees stay at BNL.
        for stage in ['pedestal','mip']+STAGES[3:]+['final']:
            for p in (root/key/stage).glob('*_calib.txt'):
                dest=out/p.relative_to(root); dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dest)
        pdf_link = '<a href="%s">PDF</a>' % summary_pdf_name(key) if args.pdf else '-'
        present = sum(p is not None for p, title, name in summaries[key])
        rows.append('<tr><td><a href="%s.html">%s</a></td><td>%s</td><td>%s</td><td>%d/27</td><td>%s</td></tr>' % (key,key.upper(), ', '.join(map(str,m['muon_runs'])), ', '.join(map(str,m['pedestal_runs'])), present, pdf_link))
    body = '<p>%s</p><p>R5 summaries follow Fredi\'s 27-page SummarySetB plot selection and order. Original PNGs fill each PDF page, with their aspect ratios preserved. Earlier stages and all other PNGs are linked from each set.</p>' % method
    body += '<p>The method label is supplied with --method; it is not inferred from campaign names or images.</p><p>Plot collection for review; no calibration-quality or external-agreement claim is made.</p>'
    if args.pdf: body += '<p><a href="ps-2026-r5-report.pdf">Download the R5 PDF report</a></p>'
    body += '<p>Pages 1-6: fit-parameter maps; 7-14: MIP spectra, layers 0-7; 15-19: trigger and signal/noise maps; 20-27: trigger primitives, layers 0-7.</p>'
    if manifest['warnings']:
        body += '<h2>Missing panels</h2><p>Missing layer plots have marked placeholder pages; their absence is not evidence of a successful or failed fit.</p><ul>' + ''.join('<li>%s</li>' % html.escape(w) for w in manifest['warnings']) + '</ul>'
    body += '<table><tr><th>Set</th><th>Muon runs</th><th>Pedestal</th><th>Summary plots</th><th>Summary</th></tr>' + ''.join(rows) + '</table>'
    body += '<p>Generated %s. <a href="manifest.json">Plot inventory and recipe notes</a></p>' % stamp
    (out/'index.html').write_text(page('PS April 2026 - calibration report',body),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    with (out/'plot-inventory.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['set','stage','path','bytes']);w.writeheader();w.writerows(manifest['plots'])
    with (out/'summary-pages.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['set','page','title','expected_file','path','status']);w.writeheader();w.writerows(manifest['summary_pages'])
    if args.pdf:
        for key, paths in pdf_groups.items():
            print('Building ' + summary_pdf_name(key) + ' (27 pages)...', flush=True)
            pdf_report(out/summary_pdf_name(key), {key: paths}, method)
        print('Building combined R5 PDF...',flush=True)
        pdf_report(out/'ps-2026-r5-report.pdf',pdf_groups,method)
    print('Creating portable ZIP...',flush=True)
    with zipfile.ZipFile(out.with_suffix('.zip'),'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,Path(out.name)/p.relative_to(out))
    print('Report: '+str(out/'index.html'))
    if args.pdf:print('PDF: '+str(out/'ps-2026-r5-report.pdf'))
    print('Download: '+str(out.with_suffix('.zip')))
    print('%d sets; %d summary pages (%d missing panels); %d total PNGs. No fits rerun.' % (len(inventory),len(manifest['summary_pages']),len(manifest['warnings']),len(manifest['plots'])))


if __name__ == '__main__':
    main()

