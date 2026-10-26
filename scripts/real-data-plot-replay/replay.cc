// Private replay adapter. All production source files are unchanged.
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <TFile.h>
#include <TTree.h>
#include <TROOT.h>
#include <TDatime.h>
#include <TLegend.h>
#include <TAxis.h>
#include <TColor.h>
#include <TCanvas.h>
#include <TLine.h>
#include <TBox.h>
#include <TPad.h>
#include <TFrame.h>
#include <TLatex.h>
#include <TGraph.h>
#include <TGraphErrors.h>
#include <TGraphAsymmErrors.h>
#include <TGaxis.h>
#include <TSystem.h>
#include <TStyle.h>
#include <TH3.h>
#include "Event.h"
#include "RootSetupWrapper.h"
#include "TileSpectra.h"
#include "CommonHelperFunctions.h"
#include "PlotHelper_general.h"
#include "FitCurveDrawing.h"
#include "reference.h"
#include "plot_functions.h"

constexpr int cell = 1344;
void demand(bool ok, const std::string& why) { if (!ok) throw std::runtime_error(why); }
bool same(double a, double b) { return a == b || (std::isnan(a) && std::isnan(b)); }

struct ReplaySpectrum : TileSpectra {
  using TileSpectra::TileSpectra;
  void use_calibration(TileCalib* final) { calib = final; }
  void restore_fit() {
    SignalHG = TF1("fmipmipTriggHGCellID1344", langaufun, reference::xmin, reference::xmax, 4);
    const char* names[] = {"Width", "MP", "Area", "GSigma"};
    for (int p=0;p<4;++p) {
      SignalHG.SetParName(p,names[p]);
      SignalHG.SetParameter(p,reference::value[p]);
      SignalHG.SetParError(p,reference::error[p]);
      SignalHG.SetParLimits(p,reference::lower[p],reference::upper[p]);
    }
    SignalHG.SetNpx(reference::npx);
    SignalHG.SetChisquare(reference::chi2);
    SignalHG.SetNDF(reference::ndf);
    bmipHG = true;
  }
};

std::unique_ptr<TFile> open_file(const char* path) {
  std::unique_ptr<TFile> f(TFile::Open(path,"READ"));
  demand(f && !f->IsZombie(),std::string("Cannot read ROOT file: ")+path);
  return f;
}
TTree* tree(TFile& f,const char* name) {
  auto* t = dynamic_cast<TTree*>(f.Get(name));
  demand(t && t->GetEntries()>0,std::string("Missing/empty tree ")+name+" in "+f.GetName());
  return t;
}
template<class T> void branch(TTree* t,const char* name,T** ptr) {
  demand(t->GetBranch(name),std::string("Missing branch ")+t->GetName()+"/"+name);
  demand(t->SetBranchAddress(name,ptr)>=0,std::string("Incompatible branch ")+name);
}
void errors_like_production(TH1D& h) {
  // Exact historical expression: intentional NaNs for empty regular bins.
  double relSysF=0.15;
  for (int b=1;b<h.GetNbinsX()+1;++b) {
    double e=TMath::Sqrt(relSysF*relSysF+TMath::Power(h.GetBinError(b)/h.GetBinContent(b),2))*h.GetBinContent(b);
    h.SetBinError(b,e);
  }
}
void compare_reference(TH1D& h) {
  demand(h.GetNbinsX()==1124,"Triggered bin count mismatch");
  demand(h.GetEntries()==reference::entries,"Triggered entries mismatch: wrong dataset/selection");
  demand(h.GetBinErrorOption()==TH1::kNormal,"Triggered error option mismatch");
  for (int b=1;b<=1125;++b)
    demand(h.GetXaxis()->GetBinLowEdge(b)==reference::edges[b-1],"Triggered bin edge mismatch");
  demand(h.GetSumw2N()==1126,"Triggered Sumw2 size mismatch");
  for (int b=0;b<=1125;++b) {
    demand(same(h.GetBinContent(b),reference::contents[b]),"Triggered content mismatch at bin "+std::to_string(b));
    demand(same(h.GetBinError(b),reference::errors[b]),"Triggered error mismatch at bin "+std::to_string(b));
    demand(same(h.GetSumw2()->At(b),reference::sumw2[b]),"Triggered Sumw2 mismatch at bin "+std::to_string(b));
  }
}
void check_fit(TF1& f) {
  demand(f.GetXmin()==reference::xmin && f.GetXmax()==reference::xmax,"Fit range changed");
  demand(f.GetNpx()==reference::npx && f.GetChisquare()==reference::chi2 && f.GetNDF()==reference::ndf,"Fit metadata changed");
  for (int p=0;p<4;++p) {
    double lo,hi;f.GetParLimits(p,lo,hi);
    demand(f.GetParameter(p)==reference::value[p] && f.GetParError(p)==reference::error[p]
      && lo==reference::lower[p] && hi==reference::upper[p],"Fit parameter metadata changed");
  }
  demand(std::isfinite(f.Eval(22.5)) && f.Eval(22.5)>0,"Restored live evaluator is not functional");
}
void fill_event(Event& event, ReplaySpectrum& inclusive,ReplaySpectrum& triggered,double avg) {
  // The same target-cell branch of Analyses::GetImprovedScaling; no ADC recalibration.
  for (int j=0;j<event.GetNTiles();++j) {
    Tile* base=event.GetTile(j);
    if (base->GetCellID()!=cell) continue;
    auto* tile=dynamic_cast<Hgcroc*>(base);
    demand(tile,"Target tile is not Hgcroc");
    double adc=tile->GetIntegratedADC(),tot=tile->GetRawTOT(),toa=tile->GetRawTOA();
    bool accepted=event.InspectIfLocalMuonTrigg(cell,avg,0.8,2.5);
    triggered.FillTrigger(tile->GetLocalTriggerPrimitive());
    inclusive.FillHGCROC(adc,toa,tot);
    if (accepted) triggered.FillHGCROC(adc,toa,tot);
  }
}
void draw_pair(const std::string& out,ReplaySpectrum& inclusive,ReplaySpectrum& triggered,
               RunInfo info,double vov,const std::string& stem) {
  // Verbatim caller settings from Analyses::GetImprovedScaling (ExtPlot>2 block).
  StyleSettingsBasics("pdf"); SetPlotStyle();
  std::map<int,TileSpectra> spectra{{cell,inclusive}},trigg{{cell,triggered}};
  check_fit(*trigg.at(cell).GetSignalModel(1));
  double maxHG=ReturnMipPlotRangeDepVov(vov,true,ReadOut::Type::Hgcroc)*1;
  demand(maxHG==250.,"Unexpected plot extent for E2");
  for (int mode=0;mode<2;++mode) {
    // Functions take maps by value. ROOT draws pointers into those temporary maps;
    // each function saves its image before its copied maps are destroyed.
    for (const char* ext : {"pdf","png"}) {
      TCanvas* canvasSTile=new TCanvas("canvasSignleTile","",0,0,1600,1300);
      DefaultCanvasSettings(canvasSTile,0.08,0.01,0.01,0.082);
      int textSizePixel=30;
      TString dest=(out+"/"+stem+(mode?"_faithful.":"_legacy.")+ext).c_str();
      if (!mode) historical_plot::PlotMipWithFitsSingleTile(canvasSTile,0.95,0.95,Double_t(textSizePixel)*2/1600.,
        textSizePixel*2,spectra,trigg,true,-100,maxHG,1.2,cell,dest,info);
      else reviewed_plot::PlotMipWithFitsSingleTile(canvasSTile,0.95,0.95,Double_t(textSizePixel)*2/1600.,
        textSizePixel*2,spectra,trigg,true,-100,maxHG,1.2,cell,dest,info);
      delete canvasSTile;
    }
  }
  check_fit(*trigg.at(cell).GetSignalModel(1));
  check_fit(*triggered.GetSignalModel(1));
}
void report(const std::string& out,const char* kind,Long64_t events,double inclusive,double triggered,double avg) {
  std::ofstream f(out+"/checks.json");
  f<<std::setprecision(17)<<"{\n\"mode\":\""<<kind<<"\",\n\"events_read\":"<<events
   <<",\n\"inclusive_entries\":"<<inclusive<<",\n\"triggered_entries\":"<<triggered
   <<",\n\"selection_average_per_tile\":"<<avg
   <<",\n\"saved_fit_unchanged\":true,\n\"reference_histogram_match\":"
   <<(std::string(kind)=="real-data"?"true":"null")<<"\n}\n";
}

int main(int argc,char** argv) try {
  demand(argc>=4,"Usage: replay MODE OUT RUNLIST [EVENTS PRIOR_CALIB FINAL_ROOT]");
  gROOT->SetBatch(kTRUE);
  std::string mode=argv[1],out=argv[2];
  auto runs=readRunInfosFromFile(argv[3],0,0);
  demand(runs.count(421) && runs.at(421).year==2026,"Pinned runlist lacks E2 run421/year2026");
  demand(mode=="replay" && argc==7,"Incorrect replay arguments");
  auto input=open_file(argv[4]);auto* setupTree=tree(*input,"Setup");RootSetupWrapper* wrapper=nullptr;
  branch(setupTree,"setup",&wrapper);demand(setupTree->GetEntry(0)>0 && wrapper,"Cannot read Setup/setup");
  demand(Setup::GetInstance()->Initialize(*wrapper),"Setup initialization failed");
  demand(Setup::GetInstance()->GetAssemblyID(cell)!="","Target cell absent from Setup");
  Calib* prior=nullptr;auto* priorTree=tree(*input,"Calib");branch(priorTree,"calib",&prior);
  demand(priorTree->GetEntry(0)>0 && prior,"Cannot read input Calib");
  prior->ReadCalibFromTextFile(argv[5],0);
  demand(prior->find(cell)!=prior->end() && prior->GetBadChannel(cell)==3,"Wrong input target calibration");
  int active=0;double avTiles=0;double avg=prior->GetAverageScaleHighPerSingleLayer(active,avTiles);
  demand(std::isfinite(avg) && avg>0,"Invalid original trigger calibration average");
  auto finalFile=open_file(argv[6]);Calib* final=nullptr;auto* finalTree=tree(*finalFile,"Calib");branch(finalTree,"calib",&final);
  demand(finalTree->GetEntry(0)>0 && final,"Cannot read final full-precision calibration");
  demand(final->find(cell)!=final->end() && final->GetRunNumber()==421 && std::abs(final->GetVov()-5.7)<1e-12,"Wrong final calibration campaign");
  TileCalib* finalTile=final->GetTileCalib(cell);
  demand(std::abs(finalTile->ScaleH-22.018432)<0.00000051 && std::abs(finalTile->ScaleWidthH-0.634287)<0.00000051,
    "Final calibration does not match saved original fit record");
  demand(finalTile->BadChannel==3 && std::abs(finalTile->PedestalSigH-1.517257)<0.00000051,
    "Final calibration noise/BC overlay differs from archived original");
  auto* data=tree(*input,"Data");Event* event=nullptr;branch(data,"event",&event);
  ReplaySpectrum inclusive("mip1st",cell,prior->GetTileCalib(cell),ReadOut::Type::Hgcroc,1),triggered("mipTrigg",cell,prior->GetTileCalib(cell),ReadOut::Type::Hgcroc,1);
  const Long64_t count=data->GetEntries();
  for(Long64_t i=0;i<count;++i) {
    demand(data->GetEntry(i)>0 && event,"Failed event read "+std::to_string(i));
    demand(event->GetROtype()==ReadOut::Type::Hgcroc,"Non-HGCROC event in selected input");
    if(i==0)demand(event->GetRunNumber()==421,"First run is not original E2 run421");
    fill_event(*event,inclusive,triggered,avg);
    if(i && i%10000==0)std::cout<<"Read "<<i<<" / "<<count<<std::endl;
  }
  errors_like_production(*inclusive.GetHG());errors_like_production(*triggered.GetHG());
  compare_reference(*triggered.GetHG()); // Hard gate: NEVER render mismatched input.
  inclusive.use_calibration(final->GetTileCalib(cell));triggered.use_calibration(final->GetTileCalib(cell));
  triggered.restore_fit();check_fit(*triggered.GetSignalModel(1));
  {TFile evidence((out+"/replayed_cell1344.root").c_str(),"RECREATE");
    inclusive.GetHG()->Write("inclusive");triggered.GetHG()->Write("triggered");
    triggered.GetSignalModel(1)->Write("saved_fit_record_NOT_a_live_callback");}
  draw_pair(out,inclusive,triggered,runs.at(421),final->GetVov(),"E2_refine5_cell1344");
  compare_reference(*triggered.GetHG());check_fit(*triggered.GetSignalModel(1));
  report(out,"real-data",count,inclusive.GetHG()->GetEntries(),triggered.GetHG()->GetEntries(),avg);
  return 0;
} catch(const std::exception& e) { std::cerr<<"ERROR: "<<e.what()<<std::endl;return 2; }
