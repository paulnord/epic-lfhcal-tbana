#!/usr/bin/env python3
"""Run the frozen protocol for one independent dataset partition."""
import argparse,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--dataset',required=True,choices=['b1','b2','e1','e2']);a=p.parse_args();script=Path(__file__).resolve().parent
for phase in ('adaptive_baseline','production_candidate'):
 subprocess.run([sys.executable,str(script/'run_fit_range_study.py'),'--bundle',str(a.bundle),'--out',str(a.out/f'{phase}-{a.dataset}'),'--datasets',a.dataset,'--phase',phase],check=True)
subprocess.run([sys.executable,str(script/'test_boundary_stability.py'),'--bundle',str(a.bundle),'--out',str(a.out/f'boundary-{a.dataset}'),'--datasets',a.dataset],check=True)
