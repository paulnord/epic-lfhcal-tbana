#!/usr/bin/env python3
"""Synthetic regression checks; no scientific data/results are generated here."""
import csv
import tempfile
from pathlib import Path
import numpy as np
from plot_boundary_convergence import read, series, PARAMETERS, flag

with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)/'b2.csv'
    rows = []
    for m in ('legacy','adaptive'):
        for n in range(9):
            row = dict(dataset='b2',stage='mip' if n==0 else 'refine%d'%n,
                       model=m,cell_id=67,execution_origin='reused_original' if n==0 else 'new_run')
            for b in ('original','valley'):
                row[b+'_saved'] = not (b=='valley' and n==2)
                for param,_ in PARAMETERS:
                    row[b+'_'+param] = 100+n if b=='original' else 98+n
            rows.append(row)
    def write():
        with p.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write()
    d,last = read(p,'b2')
    assert last==8
    y=series(d,('adaptive','valley'),67,range(1,5),'scale_h','step')
    assert np.isfinite(y[0]) and np.isnan(y[1]) and np.isnan(y[2]) and np.isfinite(y[3])
    y=series(d,('adaptive','valley'),67,[5],'scale_h','legacy-r5')
    assert np.isclose(y[0],-2/105)
    d[('adaptive','valley',67,3)]['scale_h']=0
    assert np.isnan(series(d,('adaptive','valley'),67,[4],'scale_h','step')[0])
    assert series(d,('adaptive','valley'),67,[3],'scale_h','absolute')[0]==0
    rows.pop();write()
    try: read(p,'b2')
    except ValueError: pass
    else: raise AssertionError('Incomplete B2 accepted')
    rows.append(rows[0]);write()
    try: read(p,'b2')
    except ValueError: pass
    else: raise AssertionError('Duplicate accepted')
    try: flag('?')
    except ValueError: pass
    else: raise AssertionError('Unknown saved flag accepted')
print('PASS: saved-fit gaps, fixed reference, zero denominator, incomplete B2, duplicates, flags')

# Batched drawing must never connect across missing fits, including PDF output.
import matplotlib.pyplot as plt
from plot_boundary_convergence import draw_tracks
fig,ax=plt.subplots()
draw_tracks(ax,[0,1,2,3,4],[[1,2,np.nan,4,5],[np.nan]*5],[67,68],.2)
segments=ax.collections[0].get_segments()
assert len(segments)==2
assert np.array_equal(segments[0],[[0,1],[1,2]])
assert np.array_equal(segments[1],[[3,4],[4,5]])
assert len(ax.collections[1].get_offsets())==4
assert all(c.get_rasterized() for c in ax.collections)
plt.close(fig)
print('PASS: batched drawing preserves adjacent segments, gaps and isolated points')
