#!/usr/bin/env python3
"""Rebuild case PDF books from existing PNGs, without ROOT or recalculating fits.

Uses Matplotlib, already required by the convergence plotter. Keeps all originals.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rebuild(source, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    source, out = source.resolve(), out.resolve()
    archive = Path(str(out)+'.zip')
    if out.exists() or archive.exists():
        raise ValueError('Use a new output directory and ZIP name; originals are preserved')
    manifest_path = source/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    books, sizes = {}, {}
    for dataset, cells in manifest['cases'].items():
        if dataset not in ('b1', 'b2', 'e1'):
            raise ValueError('Unexpected dataset: '+dataset)
        pages = []
        for cell in cells:
            for boundary in ('original', 'valley'):
                for method in ('legacy', 'adaptive'):
                    path = source/f'{dataset}-cell{int(cell)}-{boundary}-{method}.png'
                    image = plt.imread(path)
                    h, w = image.shape[:2]
                    if h < 100 or w < 100:
                        raise ValueError('Invalid PNG dimensions: '+str(path))
                    sizes[str(path)] = [w, h]
                    pages.append(path)
        if not pages:
            raise ValueError('No cells for '+dataset)
        books[dataset] = pages
    if not books:
        raise ValueError('No case books in manifest')
    out.mkdir(parents=True)
    provenance = dict(operation='PDF books rebuilt from unchanged PNG pages; no refitting or curve evaluation',
                      source_manifest=str(manifest_path), source_manifest_sha256=sha(manifest_path),
                      script_sha256=sha(Path(__file__)), books={})
    for dataset, pages in books.items():
        dest = out/f'{dataset}-cases.pdf'
        print(f'{dataset.upper()}: rebuilding {len(pages)} pages', flush=True)
        with PdfPages(dest, metadata={'Title': dataset.upper()+' saved-fit histories',
                                     'Subject': 'Rebuilt from original PNGs; no fit changes'}) as pdf:
            for path in pages:
                image = plt.imread(path)
                w, h = sizes[str(path)]
                fig = plt.figure(figsize=(w/150., h/150.), dpi=150)
                ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
                ax.imshow(image, interpolation='none', aspect='equal')
                pdf.savefig(fig, dpi=150)
                plt.close(fig)
        provenance['books'][dest.name] = dict(pages=len(pages),
            pngs=[dict(path=str(path), sha256=sha(path), pixels=sizes[str(path)]) for path in pages])
    (out/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(out.iterdir()): z.write(path, out.name+'/'+path.name)
    print('Download:', archive, flush=True)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True, type=Path, help='Existing interesting-cases directory')
    p.add_argument('--out', required=True, type=Path, help='New directory for repaired PDF books')
    a = p.parse_args(); rebuild(a.input, a.out)


if __name__ == '__main__':
    main()
