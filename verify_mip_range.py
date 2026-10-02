#!/usr/bin/env python3
"""Parity check: C++ implementation versus frozen SciPy rule on uploaded spectra."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fit-range-study'))
from run_fit_range_study import setup_case,smoothed_valley
p=argparse.ArgumentParser();p.add_argument('--bundle',action='append',type=Path,required=True);a=p.parse_args()
import ROOT
ROOT.gROOT.SetBatch(True);assert ROOT.gInterpreter.Declare('#include '+json.dumps(str((Path(__file__).with_name('MipRangeFinder.h') if Path(__file__).with_name('MipRangeFinder.h').exists() else Path(__file__).parent/'NewStructure/MipRangeFinder.h').resolve())))
records=[]
for b in a.bundle:
 m=json.loads((b/'manifest.json').read_text());f=ROOT.TFile.Open(str(b/'histograms.root'))
 for c in m['cases']:
  h=f.Get(c['root_path']);s=setup_case(ROOT,b,m,c,h);expected=smoothed_valley(h,s,2.)
  actual=ROOT.lfhcal.mip_range_v1.choose([h.GetBinCenter(i) for i in range(1,h.GetNbinsX()+1)],[h.GetBinContent(i) for i in range(1,h.GetNbinsX()+1)],s['ped'],s['avg'],s['xmin'])
  assert actual.usable==expected['usable'],(c['root_path'],actual.reason,expected)
  assert abs(actual.lower-expected.get('lower',s['xmin']))<1e-12,(c['root_path'],actual.lower,expected)
  for k,attr in [('observed_peak','observed'),('valley','valley'),('valley_fraction','fraction')]:
   if k in expected:assert abs(getattr(actual,attr)-expected[k])<1e-12,(c['root_path'],k)
  records.append(dict(path=c['root_path'],usable=actual.usable,lower=actual.lower,status=str(actual.reason)))
 f.Close()
print(json.dumps(dict(verified=len(records),records=records),indent=2))
