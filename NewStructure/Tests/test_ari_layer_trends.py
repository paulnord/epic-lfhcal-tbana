"""Optional regression test using a local archived manifest (Python stdlib only).
Usage: python3 test_ari_layer_trends.py EXECUTABLE MANIFEST RUN_DATABASE
Synthetic run331 is strictly test-only; no test results are scientific outputs.
"""
import csv, pathlib, subprocess, sys, tempfile
exe, manifest, db = map(lambda x: pathlib.Path(x).resolve(), sys.argv[1:])
def run(*args, good=True):
    p = subprocess.run([str(exe), *map(str,args)], capture_output=True, text=True)
    assert (p.returncode == 0) == good, p.stdout+p.stderr
    return p
with tempfile.TemporaryDirectory(prefix='ari-regression-') as td:
    base=pathlib.Path(td); rows=list(csv.DictReader(manifest.open()))
    out=base/'manifest.csv'
    with out.open('w') as f:
        w=csv.writer(f); w.writerow(['run','measurements_csv'])
        for r in rows: w.writerow([r['run'],manifest.parent/r['measurements_csv']])
        # Synthetic copied nominal widths exercise membership, NOT reanalysis.
        nominal=next(r for r in rows if r['run']=='298')
        cells=list(csv.DictReader((manifest.parent/nominal['measurements_csv']).open()))
        fake=base/'WaveformGrid_Run331_Measurements.csv'
        with fake.open('w') as g:
            cw=csv.DictWriter(g,fieldnames=cells[0].keys());cw.writeheader()
            for cell in cells: cell['run']='331';cw.writerow(cell)
        w.writerow([331,fake])
    result=run(out,db,base/'plots')
    assert 'RF7/run331 included' in result.stdout
    fits=list(csv.DictReader((base/'plots/linear_fits.csv').open()))
    assert all(r['n']=='14' for r in fits if r['scan']=='RF' and r['selection']=='diagnostic_reference')
    run(out,db,base/'plots',good=False)
    run('--make-manifest',base,base/'discovered.csv')
    discovered=list(csv.DictReader((base/'discovered.csv').open()));assert len(discovered)==1 and discovered[0]['run']=='331'
    duplicate=base/'duplicate';duplicate.mkdir();(duplicate/fake.name).write_bytes(fake.read_bytes())
    run('--make-manifest',base,base/'duplicate.csv',good=False)
print('Synthetic331 inclusion, RF fit count, manifest discovery, duplicate rejection, output protection: passed')
