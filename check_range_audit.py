#!/usr/bin/env python3
"""ROOT audit integration: range record must agree with the serialized TF1."""
from pathlib import Path
import csv,json,sys
import ROOT
ROOT.gROOT.SetBatch(True)
p=Path(__file__).resolve().parent;sys.path.insert(0,str(p));import boundary_fullchains as w
out=p/'boundary-fixture/prepared';b=w.base_module(out);paths=b.paths(out,'legacy','b1','refine1');d=paths['directory']
input=next(q for q in (p/'range-study-real/fit-range-study-inputs-20261001-v2',p.parent/'range-study-real/fit-range-study-inputs-20261001-v2') if q.is_dir());m=json.loads((input/'manifest.json').read_text());source=ROOT.TFile.Open(str(input/'histograms.root'));c=next(c for c in m['cases'] if c['dataset']=='b1' and c['cell_id']==67 and c['model']=='legacy');h=source.Get(c['root_path']);f=source.Get(c['root_path'].rsplit('/',1)[0]+'/saved_fit');f.SetRange(18.5,f.GetXmax())
r=ROOT.TFile(str(paths['root']),'RECREATE');r.Write();r.Close();r=ROOT.TFile(str(paths['hists']),'RECREATE');r.mkdir('IndividualCellsTrigg').cd();h.Write('hspectramipTriggADCCellID67');f.Write('fmipmipTriggHGCellID67');r.Close();source.Close()
lines=(input/'context/b1/legacy/current-calibration.txt').read_text().splitlines();paths['calib'].write_text('\n'.join(line for line in lines if line.split() and line.split()[0] in ('67','68'))+'\n')
log='LFHCAL_RANGE_V1 cell=67 sample=mipTrigg status=raised usable=1 old=14.5 new=18.5 peak=49.5 valley=18.5 fraction=0.02\n';(d/'DataPrep.log').write_text(log)
w.audit(b,out,'legacy','b1','refine1');rows={int(r['cell_id']):r for r in csv.DictReader(paths['report'].open())};assert rows[67]['range_status']=='raised';assert rows[68]['carried_forward']=='True';assert rows[68]['range_status']=='not_attempted'
(d/'DataPrep.log').write_text(log.replace('new=18.5','new=19.5'))
try:w.audit(b,out,'legacy','b1','refine1')
except ValueError as e:assert 'Saved fit range differs' in str(e)
else:raise AssertionError('Audit accepted incorrect fit boundary')
print('PASS: ROOT TF1 range matches diagnostics; carried-forward counted; mismatch rejected.')
