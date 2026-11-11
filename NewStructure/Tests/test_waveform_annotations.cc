#include "WaveformAnnotations.h"
#include <TROOT.h>
#include <TUUID.h>
#include <filesystem>
#include <memory>
#include <iostream>
#include <sstream>

namespace {
int checks=0;
void Check(bool ok,const char* message) {
  ++checks;if(!ok)throw std::runtime_error(std::string("FAIL: ")+message);
}
TProfile Profile(const char* name,const std::vector<double>& values,double xmin=0.) {
  TProfile p(name,"source title",values.size(),xmin,xmin+values.size());p.SetDirectory(nullptr);
  for(size_t i=0;i<values.size();++i)p.Fill(xmin+i+.5,values[i]);return p;
}
std::vector<TLine*> Lines(TPad* pad) {
  std::vector<TLine*> result;TIter next(pad->GetListOfPrimitives());
  while(auto* object=next())if(auto* line=dynamic_cast<TLine*>(object))result.push_back(line);
  return result;
}
TProfile* Display(TPad* pad) {
  TIter next(pad->GetListOfPrimitives());
  while(auto* object=next())if(auto* p=dynamic_cast<TProfile*>(object))return p;
  return nullptr;
}
TPad* CellPad(TCanvas& c,int number=1) {
  auto* grid=dynamic_cast<TPad*>(c.GetListOfPrimitives()->FindObject("waveform_grid"));
  Check(grid!=nullptr,"grid exists");return dynamic_cast<TPad*>(grid->GetPad(number));
}
std::string Bytes(const std::filesystem::path& p) {
  std::ifstream input(p,std::ios::binary);return {std::istreambuf_iterator<char>(input),{}};
}
bool HasText(TPad& pad,const std::string& wanted) {
  TIter next(pad.GetListOfPrimitives());
  while(auto* object=next())if(auto* text=dynamic_cast<TLatex*>(object))
    if(std::string(text->GetTitle()).find(wanted)!=std::string::npos)return true;
  return false;
}
bool HasLine(TPad& pad,const char* name) {
  for(auto* line:Lines(&pad))if(line->GetUniqueID()==TString(name).Hash())return true;
  return false;
}
}

int main(int argc,char** argv) {
try {
  gROOT->SetBatch(true);
  auto pulse=Profile("pulse",{0,2,6,10,6,2,0},-4.);
  const auto original=TileSpectra::MeasureWaveform(&pulse,200.,false);
  Check(original.hasPeak&&original.hasFWHM&&original.fwhm==4.,"original noninterpolated measurement");
  std::vector<lfhcal::WaveformAnnotationCell> cells;
  for(int i=0;i<64;++i)cells.push_back({1152+i,&pulse,original});
  const double entries=pulse.GetEntries(),content=pulse.GetBinContent(4);
  const int color=pulse.GetLineColor(),first=pulse.GetXaxis()->GetFirst(),last=pulse.GetXaxis()->GetLast();
  TCanvas canvas("annotation_test","",1600,1200);
  lfhcal::DrawWaveformGridPage(canvas,cells,0,0,false,false,"SYNTHETIC TEST");
  Check(Lines(CellPad(canvas)).empty(),"unmarked companion has no guides");
  const auto xmin=Display(CellPad(canvas))->GetXaxis()->GetFirst();
  const auto ymax=Display(CellPad(canvas))->GetMaximum();
  lfhcal::DrawWaveformGridPage(canvas,cells,0,0,true,false,"SYNTHETIC TEST");
  auto* pad=CellPad(canvas);const auto lines=Lines(pad);
  Check(lines.size()==4,"four guides, not five");
  int vertical=0,horizontal=0;std::set<int> styles,colors;
  for(auto* line:lines) {
    if(line->GetX1()==line->GetX2()) {
      ++vertical;styles.insert(line->GetLineStyle());colors.insert(line->GetLineColor());
      Check(line->GetX1()==original.peakTime||line->GetX1()==original.leftCrossing||line->GetX1()==original.rightCrossing,"vertical at an extracted bin center");
    } else {
      ++horizontal;Check(line->GetY1()==original.amplitude&&line->GetY2()==original.amplitude,"horizontal at peak, not half");
      Check(line->GetX1()==pad->GetUxmin()&&line->GetX2()==pad->GetUxmax(),"guide stays in actual frame on short axes");
    }
  }
  Check(vertical==3&&horizontal==1&&styles.size()==3&&colors.size()==3,"distinct three-vertical one-horizontal convention");
  Check(Display(pad)->GetXaxis()->GetFirst()==xmin&&Display(pad)->GetMaximum()==ymax,"companions share axes");
  lfhcal::DrawWaveformGridPage(canvas,cells,0,0,true,true,"SYNTHETIC TEST");
  pad=CellPad(canvas);Check(Display(pad)!=&pulse&&Display(pad)->GetBinContent(4)==1.,"normalized detached clone persists");
  for(auto* line:Lines(pad))if(line->GetX1()!=line->GetX2())Check(line->GetY1()==1.,"normalized horizontal at one");

  auto missingRight=Profile("missing_right",{0,1,4,8,9});
  const auto invalid=TileSpectra::MeasureWaveform(&missingRight);
  Check(invalid.hasPeak&&!invalid.hasFWHM,"fixture has peak and undefined width");
  canvas.Clear();canvas.cd();lfhcal::DrawWaveformGuides(invalid,0,5,0,12);
  Check(Lines(&canvas).size()==2,"undefined width retains only valid peak guides");
  canvas.Clear();canvas.cd();lfhcal::DrawWaveformGuides(WaveformMeasurement{},0,5,0,12);
  Check(Lines(&canvas).empty(),"missing profile has no guides");
  auto early=Profile("early",{0,2,6,10,6,2,0},-50.);
  std::vector<lfhcal::WaveformAnnotationCell> earlyCells={{7,&early,TileSpectra::MeasureWaveform(&early)}};
  Check(lfhcal::WaveformGridRange(earlyCells).xmin < -48.5,"negative landmarks stay visible");
  std::vector<double> lateValues(240,0.);lateValues[50]=10.;lateValues[230]=1000.;
  auto late=Profile("late_noise",lateValues,-20.);
  std::vector<lfhcal::WaveformAnnotationCell> lateCells={{8,&late,TileSpectra::MeasureWaveform(&late)}};
  Check(lfhcal::WaveformGridRange(lateCells).ymax<20.,"post-search noise does not flatten original-scale grid");

  // This is a display-only contract: consume supplied results, never remeasure.
  auto supplied=original;supplied.peakTime=17.25;
  canvas.Clear();canvas.cd();lfhcal::DrawWaveformGuides(supplied,-20,220,0,12);
  bool usedSupplied=false;for(auto* line:Lines(&canvas))if(line->GetUniqueID()==TString("waveform_peak_time").Hash())usedSupplied=line->GetX1()==17.25;
  Check(usedSupplied,"uses passed measurement object instead of a new extractor");

  // Geometry is decoded from cell IDs, never inferred from input position.
  const int bases[]={1152,1216,1408,1472,1536,1600,1792,1856};
  std::vector<std::unique_ptr<TProfile>> profiles;
  std::vector<lfhcal::WaveformAnnotationCell> geometry;
  for(int base:bases)for(int layer=0;layer<8;++layer) {
    const double a=base==1152&&layer==0?1000.:10.*(layer+1);
    profiles.emplace_back(new TProfile(Profile(Form("geometry_%d",base+layer),{0,.2*a,.6*a,a,.6*a,.2*a,0},-4.)));
    const auto measured=TileSpectra::MeasureWaveform(profiles.back().get());
    geometry.push_back({base+layer,profiles.back().get(),measured});
  }
  // A missing width does not veto its finite peak or high-peak range flag.
  geometry[0].measurement.hasFWHM=false;
  geometry[0].measurement.status=invalid.status;
  std::reverse(geometry.begin(),geometry.end());
  const auto layout=lfhcal::WaveformGridLayout(geometry);
  Check(layout.geometry&&layout.layers.front()==0&&layout.layers.back()==7,"rectangular cell-ID geometry recognized");
  for(size_t i=0;i<64;++i)
    Check(geometry[layout.order[i]].cell==bases[i/8]+int(i%8),"shuffled input has deterministic geometry order");
  Check(!lfhcal::WaveformGridLayout(cells).geometry,"64 layers at one position use input-order fallback");
  auto irregular=geometry;irregular.pop_back();
  Check(!lfhcal::WaveformGridLayout(irregular).geometry,"incomplete rectangle falls back without dropping a cell");
  irregular=geometry;irregular[0].cell=2048;
  Check(!lfhcal::WaveformGridLayout(irregular).geometry,"extra detector position is not mislabeled");
  auto sparseLayers=geometry;
  for(auto& c:sparseLayers)c.cell+=8;
  const auto actualLayers=lfhcal::WaveformGridLayout(sparseLayers);
  Check(actualLayers.geometry&&actualLayers.layers.front()==8&&actualLayers.layers.back()==15,"headers use actual layer IDs");

  const auto fullPlan=lfhcal::WaveformGridScalePlan(geometry,lfhcal::WaveformScale::Layer);
  const auto robustPlan=lfhcal::WaveformGridScalePlan(geometry,lfhcal::WaveformScale::RobustLayer);
  Check(fullPlan.layers.at(0).ymax>1000.&&fullPlan.layers.at(1).ymax<25.,"large peak affects only its layer");
  Check(robustPlan.layers.at(0).ymax<15.&&robustPlan.highPeakOutliers==std::set<int>{1152},"zero-IQR high peak omitted only from robust upper scale");
  std::vector<lfhcal::WaveformAnnotationCell> few;
  for(int i=0;i<4;++i) {
    auto c=geometry.back();c.cell=i;c.measurement.amplitude=i==3?1000.:10.;few.push_back(c);
  }
  Check(lfhcal::WaveformHighPeakOutliers(few)==std::set<int>{3},"four-peak upper fence works");
  few.pop_back();few.back().measurement.amplitude=1000.;
  Check(lfhcal::WaveformHighPeakOutliers(few).empty(),"fewer than four peaks preserve full upper scale");
  std::vector<lfhcal::WaveformAnnotationCell> inclusive;
  for(int i=0;i<8;++i) {
    auto c=geometry.back();c.cell=i;c.measurement.amplitude=i<4?1.:i<7?3.:6.;inclusive.push_back(c);
  }
  Check(lfhcal::WaveformHighPeakOutliers(inclusive).empty(),"peak exactly on Tukey upper fence retained");
  inclusive.back().measurement.amplitude=6.01;
  Check(lfhcal::WaveformHighPeakOutliers(inclusive)==std::set<int>{7},"strictly above upper fence flagged");
  auto negative=Profile("negative_outlier",{-250.,0,6,1000.,6,0,0});
  auto negMeasurement=TileSpectra::MeasureWaveform(&negative);
  std::vector<lfhcal::WaveformAnnotationCell> withNegative={{1,&negative,negMeasurement},{2,&pulse,original}};
  const auto negRange=lfhcal::WaveformGridRange(withNegative,{1});
  Check(negRange.ymin<-250.&&negRange.ymax<1000.,"negative excursion retained on upper-range outlier");
  auto suppliedAmplitude=geometry;suppliedAmplitude.back().measurement.amplitude=5000.;
  Check(lfhcal::WaveformGridScalePlan(suppliedAmplitude,lfhcal::WaveformScale::Layer).layers.at(0).ymax>5000.,"supplied peak controls upper range without remeasurement");

  lfhcal::DrawWaveformGridPage(canvas,geometry,0,0,false,false,"SYNTHETIC TEST",lfhcal::WaveformScale::Layer);
  Check(HasText(canvas,"Layer 0")&&HasText(canvas,"Layer 7")&&HasText(canvas,"Module 2"),"column and row headers rendered");
  Check(HasText(*CellPad(canvas,1),"1152")&&HasText(*CellPad(canvas,64),"1863"),"pad labels match geometry order");
  Check(Display(CellPad(canvas,1))->GetMaximum()==Display(CellPad(canvas,9))->GetMaximum(),"same column shares absolute scale");
  Check(Display(CellPad(canvas,1))->GetMaximum()>Display(CellPad(canvas,2))->GetMaximum(),"different layers have independent scales");
  lfhcal::DrawWaveformGridPage(canvas,geometry,0,0,false,false,"SYNTHETIC TEST",lfhcal::WaveformScale::RobustLayer);
  const double robustY=Display(CellPad(canvas,1))->GetMaximum();
  Check(HasLine(*CellPad(canvas,1),"waveform_clip_high")&&HasText(*CellPad(canvas,1),"A=1000 ADC")&&HasText(*CellPad(canvas,1),"scale only"),"robust outlier has clipped marker, original measured peak and range-only flag");
  lfhcal::DrawWaveformGridPage(canvas,geometry,0,0,true,false,"SYNTHETIC TEST",lfhcal::WaveformScale::RobustLayer);
  Check(Display(CellPad(canvas,1))->GetMaximum()==robustY,"robust companions have identical scales");
  Check(!HasLine(*CellPad(canvas,1),"waveform_peak_amplitude"),"off-scale peak guide omitted rather than clamped");
  for(auto* line:Lines(CellPad(canvas,1))) {
    Check(line->GetY1()>=CellPad(canvas,1)->GetUymin()&&line->GetY1()<=CellPad(canvas,1)->GetUymax()&&
          line->GetY2()>=CellPad(canvas,1)->GetUymin()&&line->GetY2()<=CellPad(canvas,1)->GetUymax(),"guides and clip markers stay within own y frame");
  }
  lfhcal::DrawWaveformGridPage(canvas,geometry,0,0,true,true,"SYNTHETIC TEST");
  Check(Display(CellPad(canvas,1))->GetMaximum()==1.12&&Display(CellPad(canvas,1))->GetBinContent(4)==1.,"normalized view unchanged with geometry layout");
  lfhcal::DrawWaveformGridPage(canvas,geometry,0,0,false,false,"SYNTHETIC TEST");
  Check(Display(CellPad(canvas,1))->GetMaximum()==Display(CellPad(canvas,64))->GetMaximum(),"global full-range companion retains common scale");
  lfhcal::DrawWaveformGridPage(canvas,geometry,0,8,false,false,"SYNTHETIC TEST",lfhcal::WaveformScale::Layer);
  Check(!HasText(canvas,"Layer 0")&&HasText(*CellPad(canvas,1),std::to_string(geometry[8].cell)),"nonzero direct-call offset falls back to truthful input-order labels");

  cells.push_back({999,nullptr,WaveformMeasurement{}});
  lfhcal::DrawWaveformGridPage(canvas,cells,0,64,true,false,"SYNTHETIC TEST");
  Check(Display(CellPad(canvas))==nullptr,"next page labels missing profile explicitly");
  bool refused=false;auto duplicate=cells;duplicate.push_back(cells.front());
  try{lfhcal::ValidateWaveformAnnotationCells(duplicate);}catch(const std::runtime_error&){refused=true;}
  Check(refused,"duplicate cells refused");
  auto corrupt=cells;corrupt[0].measurement.amplitude=std::numeric_limits<double>::quiet_NaN();refused=false;
  try{lfhcal::ValidateWaveformAnnotationCells(corrupt);}catch(const std::runtime_error&){refused=true;}
  Check(refused,"nonfinite supplied measurement refused");

  TUUID id;const bool retain=argc>1;
  const std::filesystem::path output=retain?argv[1]:(std::filesystem::temp_directory_path()/std::string("lfhcal-waveform-"+std::string(id.AsString())));
  std::filesystem::create_directories(output);
  cells.resize(64);const std::string base=(output/"SYNTHETIC_WaveformGrid").string();
  Float_t oldPaperX,oldPaperY;gStyle->GetPaperSize(oldPaperX,oldPaperY);
  lfhcal::WriteWaveformAnnotationGrid(cells,0,base,"synthetic \"fixture\", not beam data","SYNTHETIC TEST");
  Float_t newPaperX,newPaperY;gStyle->GetPaperSize(newPaperX,newPaperY);
  Check(oldPaperX==newPaperX&&oldPaperY==newPaperY,"paper size restored after export");
  Check(Bytes(base+"_Original.pdf").rfind("%PDF",0)==0&&Bytes(base+"_Annotated.pdf").rfind("%PDF",0)==0,"both PDF variants written");
  const auto csv=Bytes(base+"_Measurements.csv");
  Check(std::count(csv.begin(),csv.end(),'\n')==65,"one exact CSV record per cell");
  Check(csv.find("\"synthetic \"\"fixture\"\", not beam data\"")!=std::string::npos,"CSV source escaped");
  Check(csv.find(",10,-0.5,-2.5,1.5,4,")!=std::string::npos,"CSV contains unchanged measurement values");
  const auto before=Bytes(base+"_Original.pdf");refused=false;
  try{lfhcal::WriteWaveformAnnotationGrid(cells,0,base,"test");}catch(const std::runtime_error&){refused=true;}
  Check(refused&&Bytes(base+"_Original.pdf")==before,"existing output refused without overwrite");
  canvas.Clear();
  Check(pulse.GetEntries()==entries&&pulse.GetBinContent(4)==content&&pulse.GetLineColor()==color&&
    pulse.GetXaxis()->GetFirst()==first&&pulse.GetXaxis()->GetLast()==last&&std::string(pulse.GetTitle())=="source title","source content/style/entries/range unchanged");
  const auto after=TileSpectra::MeasureWaveform(&pulse);
  Check(after.amplitude==original.amplitude&&after.peakTime==original.peakTime&&after.fwhm==original.fwhm&&after.status==original.status,"physics values unchanged after plotting");
  const auto geometryCsvOrder=geometry.front().cell;
  lfhcal::WriteWaveformAnnotationGrid(geometry,0,(output/"SYNTHETIC_GeometryGrid").string(),"synthetic geometry, not beam data","SYNTHETIC GEOMETRY TEST");
  Check(geometry.front().cell==geometryCsvOrder&&geometry.back().measurement.amplitude==1000.,"geometry export leaves input order and supplied measurements unchanged");
  const auto geometryCsv=Bytes(output/"SYNTHETIC_GeometryGrid_Measurements.csv");
  Check(geometryCsv.find("\n0,1863,")!=std::string::npos&&std::count(geometryCsv.begin(),geometryCsv.end(),'\n')==65,"CSV preserves original input population and ordering");
  if(!retain)std::filesystem::remove_all(output);
  std::cout<<"PASS: "<<checks<<" waveform annotation checks\n";return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
