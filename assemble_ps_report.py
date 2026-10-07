#!/usr/bin/env python3
"""Package existing PS-2026 calibration PNGs; never run fits or touch inputs."""
import argparse
import csv
import html
import json
import re
import shutil
import sys
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
METHOD = 'Adaptive HG fitting; original fit boundary'
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


def pdf_report(path, groups, meta, stamp):
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader
    c = Canvas(str(path), pagesize=(1000, 750))
    c.setTitle('PS April 2026 - calibration plot report')
    c.setAuthor('Paul Nord')
    def footer():
        c.setFont('Helvetica', 10)
        c.drawString(32, 18, 'PS April 2026 | ' + METHOD)
        c.drawRightString(968, 18, str(c.getPageNumber()))
    def text_page(title, lines, bookmark):
        c.bookmarkPage(bookmark)
        c.addOutlineEntry(title, bookmark, 0)
        c.setFont('Helvetica-Bold', 23)
        c.drawString(40, 700, title)
        y = 655
        c.setFont('Helvetica', 13)
        for line in lines:
            for wrapped in textwrap.wrap(line, 115) or ['']:
                if y < 55:
                    footer(); c.showPage(); y = 700; c.setFont('Helvetica', 13)
                c.drawString(40, y, wrapped); y -= 20
            y -= 8
        footer(); c.showPage()
    text_page('PS April 2026 - calibration plots', [METHOD,
        'Standard R5 summary maps and spectrum panels with the existing fit overlays. One original PNG per page.',
        'This is a plot collection for review, not a validation of calibration quality or agreement with an external standard.',
        'Campaign names contain legacy-original, but the running HGCROC HG fitter was identified as adaptive.',
        'Run and pedestal notes below describe the input recipe. They are not new conclusions from these plots.',
        'Pedestal, transfer, initial MIP and R1-R4 plots are available in the HTML appendix.',
        'Generated ' + stamp], 'intro')
    for key, paths in groups.items():
        m = meta[key]
        text_page(key.upper() + ' - R5', [
            'Muon runs: ' + ', '.join(map(str, m['muon_runs'])),
            'Pedestal runs: ' + ', '.join(map(str, m['pedestal_runs'])),
            'Pedestal association in recipe: ' + m['pedestal_evidence'],
            'Recipe notes:'] + (m['notes'] or ['None recorded.']) +
            ['R5 plot pages: %d' % len(paths)], key)
        for p, label in paths:
            im = ImageReader(str(p)); w, h = im.getSize()
            scale = min(936 / w, 640 / h)
            c.setFont('Helvetica-Bold', 13)
            c.drawString(32, 724, key.upper() + ' | R5')
            c.setFont('Helvetica', 9)
            c.drawString(32, 706, label[:160])
            c.drawImage(im, (1000-w*scale)/2, 44+(640-h*scale)/2,
                        width=w*scale, height=h*scale, mask='auto')
            footer(); c.showPage()
    c.save()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', required=True, type=Path, help='CALWORK with ps-a1 ... ps-i2')
    ap.add_argument('--out', required=True, type=Path, help='New report directory')
    ap.add_argument('--pdf', action='store_true', help='Also make bookmarked R5 PDF (requires reportlab)')
    ap.add_argument('--sets', nargs='+', choices=sorted(CATALOG), default=sorted(CATALOG))
    args = ap.parse_args()
    if args.pdf:
        try:
            import reportlab  # noqa: F401
        except ImportError:
            ap.error('--pdf needs reportlab: python3 -m pip install --user reportlab')
    root, out = args.root.resolve(), args.out.resolve()
    if out.exists() or out.with_suffix('.zip').exists():
        ap.error('Output or ZIP already exists; choose a new --out directory.')
    inventory, problems = {}, []
    for key in args.sets:
        stages = {}
        for stage in STAGES:
            stages[stage] = sorted((root/key/'plots'/stage).rglob('*.png'), key=natural)
        if not stages['refine5']:
            problems.append(key + ': no R5 PNGs')
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
    manifest = {'created_utc': stamp, 'source_root': str(root), 'method': METHOD,
                'recipe_metadata': {k: CATALOG[k] for k in args.sets}, 'plots': []}
    rows, pdf_groups = [], {}
    for key, stages in inventory.items():
        print('Packaging ' + key, flush=True)
        m = CATALOG[key]
        intro = '<p><a href="index.html">All sets</a></p><p>%s</p>' % METHOD
        intro += '<p>Muon runs: %s<br>Pedestal runs: %s<br>Pedestal association: %s</p>' % (
            ', '.join(map(str,m['muon_runs'])), ', '.join(map(str,m['pedestal_runs'])), html.escape(m['pedestal_evidence']))
        intro += '<h2>Recipe notes</h2><ul>' + ''.join('<li>%s</li>' % html.escape(n) for n in m['notes']) + '</ul>'
        intro += '<p>These notes describe the source recipe, not findings from this report.</p>'
        links, stage_figures = [], {}
        for stage, paths in stages.items():
            figs = []
            for p in paths:
                rel = p.relative_to(root)
                dest = out/rel; dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
                label = p.relative_to(root/key/'plots'/stage).as_posix()
                figs.append(figure(rel, label))
                manifest['plots'].append({'set':key, 'stage':stage, 'path':rel.as_posix(), 'bytes':dest.stat().st_size})
            stage_figures[stage] = ''.join(figs)
            stage_name = key + '-' + stage + '.html'
            (out/stage_name).write_text(page(key.upper()+' - '+stage, '<p><a href="%s.html">Back to set</a></p>' % key + (''.join(figs) or '<p>No plots found for this stage.</p>')), encoding='utf-8')
            links.append('<li><a href="%s">%s (%d plots)</a></li>' % (stage_name,stage,len(paths)))
        body = intro + '<h2>All stages</h2><ul>' + ''.join(links) + '</ul><h2>Final refinement (R5)</h2>' + stage_figures['refine5']
        (out/(key+'.html')).write_text(page(key.upper(),body), encoding='utf-8')
        pdf_groups[key] = [(out/p.relative_to(root),p.relative_to(root/key/'plots'/'refine5').as_posix()) for p in stages['refine5']]
        # Text constants are small and useful alongside the report. Event trees stay at BNL.
        for stage in ['pedestal','mip']+STAGES[3:]+['final']:
            for p in (root/key/stage).glob('*_calib.txt'):
                dest=out/p.relative_to(root); dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dest)
        rows.append('<tr><td><a href="%s.html">%s</a></td><td>%s</td><td>%s</td><td>%d</td></tr>' % (key,key.upper(), ', '.join(map(str,m['muon_runs'])), ', '.join(map(str,m['pedestal_runs'])),len(stages['refine5'])))
    body = '<p>%s</p><p>Full standard R5 plot collections, with the original fit overlays. Earlier stages are linked from each set.</p>' % METHOD
    body += '<p>Campaign labels still say legacy-original. The method label above reflects the identified running HG fitter.</p><p>Plot collection for review; no calibration-quality or external-agreement claim is made.</p>'
    if args.pdf: body += '<p><a href="ps-2026-r5-report.pdf">Download the R5 PDF report</a></p>'
    body += '<table><tr><th>Set</th><th>Muon runs</th><th>Pedestal</th><th>R5 plots</th></tr>' + ''.join(rows) + '</table>'
    body += '<p>Generated %s. <a href="manifest.json">Plot inventory and recipe notes</a></p>' % stamp
    (out/'index.html').write_text(page('PS April 2026 - calibration report',body),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    with (out/'plot-inventory.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['set','stage','path','bytes']);w.writeheader();w.writerows(manifest['plots'])
    if args.pdf:
        print('Building R5 PDF from PNGs...',flush=True)
        pdf_report(out/'ps-2026-r5-report.pdf',pdf_groups,CATALOG,stamp)
    print('Creating portable ZIP...',flush=True)
    with zipfile.ZipFile(out.with_suffix('.zip'),'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,Path(out.name)/p.relative_to(out))
    print('Report: '+str(out/'index.html'))
    if args.pdf:print('PDF: '+str(out/'ps-2026-r5-report.pdf'))
    print('Download: '+str(out.with_suffix('.zip')))
    print('%d sets; %d R5 plots; %d total plots. No fits rerun.' % (len(inventory),sum(len(v) for v in pdf_groups.values()),len(manifest['plots'])))


if __name__ == '__main__':
    main()
