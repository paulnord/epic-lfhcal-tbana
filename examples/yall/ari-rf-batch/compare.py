#!/usr/bin/env python3
"""Pair declared fan-in by run identity, not argument/glob order."""
import argparse
from pathlib import Path
import re
import subprocess
p=argparse.ArgumentParser()
p.add_argument('executable'); p.add_argument('rundb'); p.add_argument('root'); p.add_argument('plots')
p.add_argument('--calibrated',nargs='+',required=True); p.add_argument('--hists',nargs='+',required=True)
a=p.parse_args()
def indexed(paths):
    result={}
    for name in paths:
        match=re.search(r'_Run_(\d+)(?:_Hists)?\.root$',name)
        if not match or match[1] in result: raise SystemExit('Invalid or duplicate run: '+name)
        if not Path(name).is_file() or not Path(name).stat().st_size: raise SystemExit('Missing/empty input: '+name)
        result[match[1]]=name
    return result
cal,hist=indexed(a.calibrated),indexed(a.hists)
if cal.keys()!=hist.keys(): raise SystemExit('Calibration/histogram run sets differ')
inputs=Path(a.root).with_name('rf_inputs.txt')
inputs.write_text(''.join(f'{cal[r]} {hist[r]}\n' for r in sorted(cal,key=int)))
subprocess.run([a.executable,'-A','-I',str(inputs),'-r',a.rundb,'-o',a.root,'-O',a.plots],check=True)
