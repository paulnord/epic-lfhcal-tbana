"""Execute the actual compiled TileSpectra fitters, without changing their code."""
from pathlib import Path
from array import array
import sys, json, re, hashlib, math, argparse

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--library',type=Path,required=True)
p.add_argument('--headers',type=Path,required=True)
p.add_argument('--bundle',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
args=p.parse_args()
args.out.parent.mkdir(parents=True,exist_ok=True)
import ROOT
ROOT.gROOT.SetBatch(True)
ROOT.gInterpreter.AddIncludePath(str(args.headers.resolve()))
assert ROOT.gSystem.Load(str(args.library.resolve())) >= 0
assert ROOT.gSystem.Load('libMinuit') >= 0
ROOT.gInterpreter.Declare(r'''
#include "TileSpectra.h"
#include "TMinuit.h"
class CheckedSpectra: public TileSpectra {
 public:
  using TileSpectra::TileSpectra;
  const TF1& rawHG() const { return SignalHG; }
  const TF1& rawLG() const { return SignalLG; }
  static void seed(int seed) { static TMinuit helper(7); double flag=3.; helper.mnrn15(flag,seed); }
  static void populate(TH1D* h, double mp, double width, double sigma, bool pedestal) {
    double pars[4]={width,mp,20000,sigma};
    for (int i=1; i<=h->GetNbinsX(); ++i) {
      double x=h->GetBinCenter(i);
      double v=langaufun(&x,pars);
      if (pedestal) v+=2000*TMath::Gaus(x,0,sigma,true);
      h->SetBinContent(i,v); h->SetBinError(i,sqrt(v));
    }
    h->SetEntries(h->Integral());
  }
};
''')
bundle=args.bundle.resolve()
manifest=json.loads((bundle/'manifest.json').read_text())
rootfile=bundle/'histograms.root'
assert hashlib.sha256(rootfile.read_bytes()).hexdigest()==manifest['histograms_root_sha256']
mapping=bundle/'campaigns/adaptive-fullchains-remaining-20260929T014858Z/sources/legacy/configs/TB2026/mapping_HGCROC_SPSH2TB_sumV2_default.csv'
assert ROOT.Setup.GetInstance().Initialize(str(mapping),0)
f=ROOT.TFile.Open(str(rootfile))
results=[]
def record(spec, cal, name, gain, improved, vov, average):
    ROOT.CheckedSpectra.seed(12345)
    ROOT.gRandom.SetSeed(12345)
    out=array('d',[-777.]*16); err=array('d',[-777.]*16)
    accepted=bool((spec.FitMipHG if gain=='HG' else spec.FitMipLG)(out,err,0,2026,improved,vov,average))
    fn=spec.rawHG() if gain=='HG' else spec.rawLG()
    result=dict(name=name,accepted=accepted,parameters=[fn.GetParameter(i) for i in range(fn.GetNpar())],errors=[fn.GetParError(i) for i in range(fn.GetNpar())],range=[fn.GetXmin(),fn.GetXmax()],chi2=fn.GetChisquare(),ndf=fn.GetNDF(),out=list(out),out_errors=list(err),calibration=[cal.ScaleH,cal.ScaleWidthH,cal.ScaleL,cal.ScaleWidthL])
    results.append(result)
    args.out.write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
    print(name,'accepted='+str(accepted),'parameters='+str(fn.GetNpar()),flush=True)

for case in manifest['cases']:
    text=(bundle/'context'/case['dataset']/case['model']/'previous-calibration.txt').read_text()
    vov=float(re.search(r'Vov:\s*([\d.]+)',text).group(1))
    rows={int(p[0]):list(map(float,p)) for line in text.splitlines() if len(p:=line.split())==18 and p[0].isdigit()}
    active=[r[9] for r in rows.values() if r[9]!=-1000 and r[17]>=2]
    row=rows[case['cell_id']]
    cal=ROOT.TileCalib()
    for attr,index in [('PedestalMeanH',5),('PedestalSigH',6),('PedestalMeanL',7),('PedestalSigL',8),('ScaleH',9),('ScaleWidthH',10),('ScaleL',11),('ScaleWidthL',12),('LGHGCorr',13),('LGHGCorrOff',14),('HGLGCorr',15)]: setattr(cal,attr,row[index])
    cal.BadChannel=int(row[17])
    spec=ROOT.CheckedSpectra('runtime',case['cell_id'],cal,ROOT.ReadOut.Type.Hgcroc,1,0)
    source=f.Get(case['root_path']); assert source
    source.Copy(spec.GetHG()); spec.GetHG().SetDirectory(0)
    assert spec.GetHG().GetEntries()==source.GetEntries()
    record(spec,cal,case['root_path'],'HG',True,vov,sum(active)/len(active))
    del spec

for gain in ('HG','LG'):
  for improved in (False,True):
    cal=ROOT.TileCalib(); cal.PedestalSigH=8.; cal.PedestalSigL=2.; cal.BadChannel=3
    spec=ROOT.CheckedSpectra('synthetic',67,cal,ROOT.ReadOut.Type.Caen,1,0)
    ROOT.CheckedSpectra.populate(spec.GetHG() if gain=='HG' else spec.GetLG(),300. if gain=='HG' else 30.,30. if gain=='HG' else 3.,8. if gain=='HG' else 2.,improved)
    record(spec,cal,'synthetic-caen-'+gain+'-improved-'+str(improved),gain,improved,4.7,300. if gain=='HG' else 30.)
    del spec
f.Close()
print('DONE',len(results),'cases',flush=True)
