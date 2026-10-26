import ctypes, hashlib, json, math, os, shlex, shutil, subprocess, sys, urllib.request
from pathlib import Path

def need(ok, why):
    if not ok: raise RuntimeError(why)
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024),b''): h.update(block)
    return h.hexdigest()
def pin(path, digest):
    need(path.is_file(), 'Missing original input: '+str(path))
    need(sha(path)==digest, 'Original input/source differs: '+str(path))
def function(text):
    start=text.index('  inline void PlotMipWithFitsSingleTile (')
    end=text.index('{',start)+1; depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}'); end+=1
    return text[start:end]
def run(args, log):
    print('+',shlex.join(map(str,args)),flush=True)
    with log.open('w') as stream: subprocess.run(list(map(str,args)),stdout=stream,stderr=subprocess.STDOUT,check=True)

C=Path(os.environ['CAMPAIGN']).resolve(); O=Path(os.environ['OUT']).resolve()
need(O!=C and C not in O.parents,'Output must be outside the original campaign')
need(O.is_dir() and {p.name for p in O.iterdir()}<={'replay.cc','run.py'},'Use a new output directory; do not overwrite earlier results')
need(C.name=='adaptive-fullchains-remaining-20260929T014858Z','Wrong campaign directory')
pin(C/'manifest.json','0000c9cf24fb886896415f54a6dbd98807d23b2512693f0efe0808e90e70f0f2')
pin(C/'source-hashes.json','59b602bc644cd09ce641cc09771472ecf4de165dfa0d6ca9dcf5b946146eace1')
S=C/'sources/legacy/NewStructure'; hashes=json.loads((C/'source-hashes.json').read_text())['legacy']
for path in S.iterdir():
    if path.is_file() and path.suffix in ('.h','.cc'):
        need('NewStructure/'+path.name in hashes,'Unrecorded source: '+str(path))
        pin(path,hashes['NewStructure/'+path.name])
events=C/'legacy/e2/select/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_FullSetE_2.root'
prior=C/'legacy/e2/refine4/rawHGCROC_wPedwMuon_wBC_Imp4R_Muon_FullSetE_2_calib.txt'
final=C/'legacy/e2/refine5/rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_FullSetE_2.root'
hists=final.with_name(final.stem+'_Hists.root')
db=C/'sources/legacy/configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv'
for path in (events,prior,final,hists,db): need(path.is_file(),'Missing original input: '+str(path))
pin(prior,'85de0f92c4082e4102ab2601217afb78452416165f333035bef298a30e59f64d')
pin(db,'ba8277483df5552a8bb16b39de6400ee0bbfbd3ecb0a292615aee86da735c17f')
rc=shutil.which('root-config'); need(rc,'Activate ROOT first: root-config missing')
config=lambda flag:subprocess.check_output([rc,flag],text=True).strip()
import ROOT
need(ROOT.gROOT.GetVersion().replace('/','.')==config('--version'),'PyROOT and root-config versions differ; activate one consistent ROOT environment')
ROOT.gROOT.SetBatch(True)
f=ROOT.TFile.Open(str(hists),'READ'); need(f and not f.IsZombie(),'Cannot open original Hists ROOT')
h=f.Get('IndividualCellsTrigg/hspectramipTriggADCCellID1344')
fit=f.Get('IndividualCellsTrigg/fmipmipTriggHGCellID1344')
need(h and fit,'Original cell1344 spectrum or saved fit missing'); n=h.GetNbinsX()
need(n==1124 and h.GetSumw2N()==1126 and fit.GetNpar()==4,'Unexpected original object shape')
num=lambda x:'NaN' if math.isnan(float(x)) else float(x)
hist=dict(class_name=h.ClassName(),nbins=n,entries=float(h.GetEntries()),
    edges=[h.GetXaxis().GetBinLowEdge(b) for b in range(1,n+2)],
    contents=[num(h.GetBinContent(b)) for b in range(n+2)],errors=[num(h.GetBinError(b)) for b in range(n+2)],
    sumw2=[num(h.GetSumw2().At(b)) for b in range(n+2)],error_option=int(h.GetBinErrorOption()))
pars=[]
for i in range(4):
    lo,hi=ctypes.c_double(),ctypes.c_double(); fit.GetParLimits(i,lo,hi)
    pars.append(dict(name=fit.GetParName(i),value=fit.GetParameter(i),error=fit.GetParError(i),lower=lo.value,upper=hi.value))
meta=dict(title=fit.GetTitle(),xmin=fit.GetXmin(),xmax=fit.GetXmax(),npx=fit.GetNpx(),
          chi2=fit.GetChisquare(),ndf=fit.GetNDF(),parameters=pars)
record=dict(histogram=hist,fit=meta)
fingerprint=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()
need(fingerprint=='0e34969ed77e0779a46d7df8f334c0f443591b27688ca677aa0d55ad67374ba8',
     'Original histogram/fit is not the independently archived cell1344 record')
(O/'original-record.json').write_text(json.dumps(record,indent=2)+'\n'); f.Close()
literal=lambda v:'std::numeric_limits<double>::quiet_NaN()' if v=='NaN' else repr(float(v))
lines=['#include <limits>','namespace reference {']
for key in ('edges','contents','errors','sumw2'):
    lines.append('const double '+key+'[] = {'+','.join(map(literal,hist[key]))+'};')
for key in ('value','error','lower','upper'):
    lines.append('const double '+key+'[] = {'+','.join(literal(p[key]) for p in pars)+'};')
for key in ('xmin','xmax','npx','chi2','ndf'): lines.append('const double '+key+' = '+literal(meta[key])+';')
lines+=['const double entries = '+literal(hist['entries'])+';','}']
(O/'reference.h').write_text('\n'.join(lines)+'\n')
revision='51a43cb548edeb6a418be037a402ae1e21387c23'
for name,digest in [('PlotHelper.h','9e2282be510fda1324dd3622dac8fa1df806f2af1429f194f3ad02db912e2c55'),
                    ('FitCurveDrawing.h','bf98550bca808b334f37da55703d26cb27878db31e06c39bc8fc4e2ee5893e61')]:
    with urllib.request.urlopen('https://raw.githubusercontent.com/eic/epic-lfhcal-tbana/'+revision+'/NewStructure/'+name,timeout=90) as response:
        (O/name).write_bytes(response.read())
    pin(O/name,digest)
old=function((S/'PlotHelper.h').read_text()); new=function((O/'PlotHelper.h').read_text())
expected=old.replace('SetStyleFit(fit , 0, 2000,','SetStyleFit(fit , -10000, -10000,')
expected=expected.replace('SetStyleFit(fit , -10000, -10000, 20, 7, kBlue+3);  ','SetStyleFit(fit , -10000, -10000, 20, 7, kBlue+3);')
expected=expected.replace('fit->Draw("same");','lfhcal::DrawMipFit(*fit, std::max(xPMin, 0.), std::min(xPMax, 2000.));')
need(new==expected,'Plot-function parity failed')
(O/'plot_functions.h').write_text('namespace historical_plot {\n'+old+'\n}\nnamespace reviewed_plot {\n'+new+'\n}\n')
names='Setup RootSetupWrapper Calib Event Tile HGCROC Caen TileSpectra'.split()
link=(S/'LinkDef.h').read_text()
for name in ('TileTrend','CalibSummary','AnaSummary','MultiCanvas'): link=link.replace('#pragma link C++ class '+name+'+;\n','')
(O/'ReplayLinkDef.h').write_text(link)
prefix=Path(rc).resolve().parent.parent
# Native ROOT unchanged; support the known local PyPI-wheel path layout for testing.
flags=lambda flag:[x.replace(str(prefix/'mock_site_packages/ROOT'),str(prefix)) for x in shlex.split(config(flag))]
libs=flags('--libs'); wheel=prefix.parent/'root.libs'
if wheel.is_dir(): libs+=['-Wl,-rpath-link,'+str(wheel),'-Wl,-rpath,'+str(wheel)]
run([prefix/'bin/rootcling','-f',O/'ReplayDict.cxx','-c','-I'+str(S)]+[S/(n+'.h') for n in names]+[O/'ReplayLinkDef.h'],O/'dictionary.log')
run(shlex.split(os.environ.get('CXX','c++'))+['-O2']+flags('--cflags')+['-I'+str(S),'-I'+str(O),O/'replay.cc',O/'ReplayDict.cxx']+
    [S/(n+'.cc') for n in names]+libs+['-Wl,-rpath,'+str(prefix/'lib'),'-o',O/'replay'],O/'build.log')
inputs={}
for path in (events,prior,final,hists):
    st=path.stat(); print('Recording input SHA256:',path,flush=True)
    inputs[str(path)]=dict(bytes=st.st_size,mtime_ns=st.st_mtime_ns,sha256=sha(path))
run([O/'replay','replay',O,db,events,prior,final],O/'run.log')
for name,record in inputs.items():
    st=Path(name).stat(); need((st.st_size,st.st_mtime_ns)==(record['bytes'],record['mtime_ns']),'Input changed during replay; discard outputs')
for kind in ('legacy','faithful'):
    for ext,magic in [('pdf',b'%PDF-'),('png',b'\x89PNG\r\n\x1a\n')]:
        path=O/('E2_refine5_cell1344_'+kind+'.'+ext)
        need(path.is_file() and path.stat().st_size>1000,'Missing output '+str(path))
        with path.open('rb') as stream: need(stream.read(len(magic))==magic,'Invalid output '+str(path))
checks=json.loads((O/'checks.json').read_text())
checks.update(full_data_run='COMPLETE',fit_calls=0,source_parity='PASS',archived_record_sha256=fingerprint,
    reviewed_renderer=revision,root_version=config('--version'),input_files=inputs,
    inclusive_reference_checksum_available=False,presentation='Original existing single-tile function; original stage generated layer pages')
(O/'checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print('COMPLETE:',O,'\nBoth original-fit renderings saved; no refit.')
