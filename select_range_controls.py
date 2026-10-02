#!/usr/bin/env python3
"""Freeze unused controls from original reports, before fitting their spectra."""
import csv,json,argparse
from pathlib import Path
from run_fit_range_study import read_calib
p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
m=json.loads((a.bundle/'manifest.json').read_text());excluded={c['cell_id'] for c in m['cases']};selection={};audit=[]
for ds in ('b1','e1','e2'):
 tables={model:{int(r['cell_id']):r for r in csv.DictReader((a.bundle/'context'/ds/model/'cells.csv').open())} for model in ('legacy','adaptive')}
 calib,_,_=read_calib(a.bundle/'context'/ds/'adaptive'/'previous-calibration.txt');selection[ds]=[]
 for layer in range(8):
  eligible=[]
  for cell,row in tables['adaptive'].items():
   if cell in excluded or int(calib[cell][1])!=layer:continue
   other=tables['legacy'][cell]
   if any(r['fit_saved']!='True' or int(r['bc'])<2 for r in (row,other)):continue
   try:
    h=float(row['scale_h']);lh=float(other['scale_h']);n=float(row['entries'])
    if not h>0 or abs(lh/h-1)>.01:continue
    if not all(float(r['fit_xmin'])<float(r['scale_h'])<float(r['fit_xmax']) for r in (row,other)):continue
   except ValueError:continue
   eligible.append((n,cell,h,lh))
  eligible.sort();assert eligible,(ds,layer);n,cell,h,lh=eligible[(len(eligible)-1)//2];selection[ds].append(cell)
  audit.append(dict(dataset=ds,layer=layer,cell=cell,entries=n,adaptive_H=h,legacy_H=lh,eligible_count=len(eligible)))
selection['b2']=selection['b1'][:]
a.out.write_text(json.dumps(dict(selection=selection,audit=audit,rule='Exclude all previously studied cell IDs. Both original fits saved, BC>=2, H inside window, legacy/adaptive H within 1%. One cell at lower median adaptive entry count per layer, ties by cell ID. B2 uses matched B1 cells without screening B2 results. These are agreement-selected controls, not an unbiased detector sample.'),indent=2)+'\n')
print(json.dumps(selection))
