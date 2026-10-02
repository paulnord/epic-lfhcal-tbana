#!/usr/bin/env python3
"""Regression checks for original-layout step plotting of boundary campaigns."""
import csv
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import matplotlib.pyplot as plt
import numpy as np
import plot_fit_parameter_convergence as p

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'reports').mkdir()
    # This deliberately incompatible sibling must not be treated as a dataset.
    (root/'reports'/'b2-boundary-comparison.csv').write_text('different,schema\n1,2\n')
    rows=[]
    for n in range(9):
        row={'stage':'mip' if n==0 else 'refine%d'%n,'cell_id':67}
        for m in p.MODELS:
            row[m+'_fit_saved']=not(n==3)
            for param,_ in p.PARAMETERS:
                row[m+'_'+param]=100+n
        rows.append(row)
    with (root/'reports'/'b2-comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    data,sources=p.load([root],[])
    assert set(data)=={'b2'}
    result=p.measures(data,['b2'],8,1e-4,4,('step',))
    assert all(r['view']=='step' for r in result)
    selected={r['stage_index']:r for r in result if r['model']=='legacy' and r['parameter']=='scale_h'}
    assert np.isclose(selected[2]['fractional_change'],1/101)
    assert 3 not in selected and not selected[4]['valid_pair']
    assert np.isclose(selected[8]['fractional_change'],1/107)
    calls=[]
    def save(fig,path,pdf):
        calls.append((path.name,fig._suptitle.get_text()))
        assert [t.get_text() for t in fig.axes[0].get_xticklabels()][:3]==['MIP→R1','R1→R2','R2→R3']
        plt.close(fig)
    argv=['plot_fit_parameter_convergence.py','--root',str(root),'--datasets','b2',
          '--out',str(root/'new'), '--steps-only','--label','new valley boundary']
    with patch.object(sys,'argv',argv),patch.object(p,'save',save):p.main()
    assert [v[0] for v in calls]==['new-step-legacy','new-step-adaptive']
    assert all('new valley boundary' in title for _,title in calls)
    assert json.loads((root/'new-sources.json').read_text())['views']==['step']
    fig,ax=plt.subplots()
    p.draw_flow_tracks(ax,np.array([1,2,3,4]),[[1,2,np.nan,4]],[67],.2)
    assert len(ax.collections[0].get_segments())==1
    assert len(ax.collections[1].get_offsets())==3
    plt.close(fig)
print('PASS: new campaign report filtering, exact adjacent-step differences, saved-fit gaps, original labels, two-figure CLI, batched lines')

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'reports').mkdir()
    rows=[]
    for m in p.MODELS:
        for n in range(9):
            row=dict(dataset='b2',stage='mip' if n==0 else 'refine%d'%n,
                     model=m,cell_id=67,original_saved=n!=3,valley_saved=n==3)
            for param,_ in p.PARAMETERS:
                row['original_'+param]=50+n
                row['valley_'+param]=500+10*n
            rows.append(row)
    report=root/'reports'/'b2-boundary-comparison.csv'
    with report.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    # A corrupt ordinary report must not be used in original-boundary mode.
    (root/'reports'/'b2-comparison.csv').write_text('unused ordinary report')
    data,sources=p.load([root],[],True)
    assert data['b2']['legacy',67,8]['scale_h']==58
    assert data['b2']['legacy',67,3]['scale_h'] is None
    changes=p.measures(data,['b2'],8,1e-4,4,('step',))
    assert np.isclose(next(r['fractional_change'] for r in changes
                          if r['model']=='adaptive' and r['parameter']=='scale_h'
                          and r['stage_index']==8),1/57)
    calls=[]
    argv=['plot_fit_parameter_convergence.py','--root',str(root),'--datasets','b2',
          '--out',str(root/'old'),'--steps-only','--original-boundary']
    with patch.object(sys,'argv',argv),patch.object(p,'save',save):p.main()
    assert [v[0] for v in calls]==['old-step-legacy','old-step-adaptive']
    assert all('original boundary' in title for _,title in calls)
    provenance=json.loads((root/'old-sources.json').read_text())
    assert provenance['boundary_source']=='frozen original fits'
print('PASS: frozen original values and saved-fit masks, B2 R8, automatic label and provenance')
