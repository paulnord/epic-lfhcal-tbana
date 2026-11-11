// Display-only replay of saved mean profiles and annotation measurements.
#include "WaveformAnnotations.h"
#include <TROOT.h>
#include <TH1.h>
#include <TColor.h>
#include <array>
#include <filesystem>
#include <iostream>
#include <memory>
#include <sstream>

namespace waveform_books {
using Row=std::vector<std::string>;
Row Split(const std::string& line) {
  Row out; std::string value; bool quoted=false;
  for(size_t i=0;i<line.size();++i) {
    char c=line[i];
    if(c=='"') { if(quoted&&i+1<line.size()&&line[i+1]=='"'){value+='"';++i;} else quoted=!quoted; }
    else if(c==','&&!quoted){out.push_back(value);value.clear();}
    else if(c!='\r')value+=c;
  }
  if(quoted)throw std::runtime_error("unclosed CSV quote");
  out.push_back(value);return out;
}
int Integer(const std::string& s){size_t n;int v=std::stoi(s,&n);if(n!=s.size())throw std::runtime_error("invalid integer: "+s);return v;}
double Number(const std::string& s){size_t n;double v=std::stod(s,&n);if(n!=s.size()||!std::isfinite(v))throw std::runtime_error("invalid number: "+s);return v;}
using Settings=std::array<int,4>;
const std::map<int,Settings> expected={
 {298,{9,7,5,1}},{300,{1,7,5,1}},{302,{2,7,5,1}},{304,{3,7,5,1}},
 {306,{4,7,5,1}},{310,{5,7,5,1}},{329,{6,7,5,1}},{333,{8,7,5,1}},
 {335,{10,7,5,1}},{337,{11,7,5,1}},{339,{12,7,5,1}},{341,{13,7,5,1}},
 {343,{14,7,5,1}},{345,{15,7,5,1}},{347,{9,7,4,1}},{349,{9,7,8,1}},
 {351,{9,7,10,1}},{353,{9,7,1,1}},{355,{9,5,5,1}},{357,{9,5,5,8}},
 {359,{9,5,5,15}},{361,{9,3,5,1}},{363,{9,5,5,1}}};
struct Group {std::string name;std::vector<int> runs;int color;};
std::vector<Group> Groups() {
  std::vector<Group> groups={{"RF",{298,300,302,304,306,310,329,333,335,337,339,341,343,345},TColor::GetColor("#176B79")},
    {"CC",{353,347,298,349,351},TColor::GetColor("#6550A1")},{"CF",{361,355,363,298},TColor::GetColor("#A86520")},
    {"CFComp",{355,357,359},TColor::GetColor("#357049")}};
  for(size_t i=0;i<groups.size();++i){const int index=i==0?0:i==1?2:i==2?1:3;
    std::sort(groups[i].runs.begin(),groups[i].runs.end(),[=](int a,int b){
      double va=i==0?80./expected.at(a)[0]:expected.at(a)[index];
      double vb=i==0?80./expected.at(b)[0]:expected.at(b)[index];return va==vb?a<b:va<vb;});}
  return groups;
}
void ValidateDatabase(const std::string& path) {
  std::ifstream in(path);if(!in)throw std::runtime_error("cannot open run database");
  std::string line;Row header;while(std::getline(in,line))if(line.rfind("Run Number,",0)==0){header=Split(line);break;}
  std::array<size_t,4> idx; const std::array<std::string,4> names={"RF","CF","CC","CFComp"};
  for(size_t i=0;i<4;++i){auto it=std::find(header.begin(),header.end(),names[i]);if(it==header.end())throw std::runtime_error("missing database setting");idx[i]=it-header.begin();}
  std::set<int> seen;while(std::getline(in,line)){if(line.empty())continue;auto r=Split(line);int run=Integer(r.at(0));if(!expected.count(run))continue;
    if(!seen.insert(run).second)throw std::runtime_error("duplicate database run");
    for(size_t i=0;i<4;++i)if(Integer(r.at(idx[i]))!=expected.at(run)[i])throw std::runtime_error("run database differs from established scan definition");}
  if(seen.size()!=expected.size())throw std::runtime_error("run database missing required runs");
}
struct Input {std::string root,csv;};
std::map<int,Input> ReadManifest(const std::string& path) {
  std::ifstream in(path);std::string line;if(!std::getline(in,line)||Split(line)!=Row{"run","profile_root","measurements_csv"})throw std::runtime_error("expected manifest header run,profile_root,measurements_csv");
  std::map<int,Input> result;const auto base=std::filesystem::absolute(path).parent_path();
  while(std::getline(in,line)){if(line.empty())continue;auto r=Split(line);if(r.size()!=3)throw std::runtime_error("manifest column count");int run=Integer(r[0]);
    if(!expected.count(run)||!result.emplace(run,Input{(base/r[1]).string(),(base/r[2]).string()}).second)throw std::runtime_error("unknown/duplicate manifest run");}
  if(result.size()!=expected.size())throw std::runtime_error("manifest must include exactly all 23 runs, including 302");return result;
}
struct Loaded {std::unique_ptr<TFile> file;std::vector<lfhcal::WaveformAnnotationCell> cells;};
Loaded Load(int run,const Input& input) {
  Loaded loaded;loaded.file.reset(TFile::Open(input.root.c_str(),"READ"));
  if(!loaded.file||loaded.file->IsZombie()||loaded.file->TestBit(TFile::kRecovered))throw std::runtime_error("unreadable/recovered ROOT file: "+input.root);
  std::ifstream in(input.csv);std::string line;
  const Row header={"run","cell","status","has_peak","has_fwhm","peak_bin","left_bin","right_bin","amplitude","peak_time_ns","left_ns","right_ns","fwhm_ns","source"};
  if(!std::getline(in,line)||Split(line)!=header)throw std::runtime_error("expected unmodified WaveformGrid Measurements CSV: "+input.csv);
  std::set<int> cells;for(int base:{1152,1216,1408,1472,1536,1600,1792,1856})for(int i=0;i<8;++i)cells.insert(base+i);
  while(std::getline(in,line)) {
    if(line.empty())continue;auto r=Split(line);if(r.size()!=14||Integer(r[0])!=run)throw std::runtime_error("CSV run/columns mismatch");
    int cell=Integer(r[1]),status=Integer(r[2]),peak=Integer(r[3]),width=Integer(r[4]);
    if(!cells.erase(cell)||status<0||status>8||peak!=(status==0||status>=4)||width!=(status==0))throw std::runtime_error("CSV cell/status/validity mismatch");
    WaveformMeasurement m;m.status=static_cast<WaveformMeasurementStatus>(status);m.hasPeak=peak;m.hasFWHM=width;
    m.peakBin=Integer(r[5]);m.leftBin=Integer(r[6]);m.rightBin=Integer(r[7]);
    if(peak){m.amplitude=Number(r[8]);m.peakTime=Number(r[9]);}else if(!r[8].empty()||!r[9].empty())throw std::runtime_error("unexpected peak values");
    if(width){m.leftCrossing=Number(r[10]);m.rightCrossing=Number(r[11]);m.fwhm=Number(r[12]);}
    else if(!r[10].empty()||!r[11].empty()||!r[12].empty())throw std::runtime_error("unexpected width values");
    auto* profile=dynamic_cast<TProfile*>(loaded.file->Get(Form("IndividualCells/waveform1DfullCellID%d",cell)));
    if((status==1)!=(profile==nullptr))throw std::runtime_error("CSV/profile presence mismatch");
    if(peak) {
      if(m.peakBin<1||m.peakBin>profile->GetNbinsX()||profile->GetBinCenter(m.peakBin)!=m.peakTime)
        throw std::runtime_error("saved peak bin/time disagree with profile axis");
      m.peakAtSearchBoundary=m.peakBin>=std::max(1,std::min(profile->GetNbinsX(),profile->GetXaxis()->FindBin(200.)))-1;
    }
    if(width&&(m.leftBin<1||m.rightBin>profile->GetNbinsX()||m.leftBin>=m.rightBin||
        profile->GetBinCenter(m.leftBin)!=m.leftCrossing||profile->GetBinCenter(m.rightBin)!=m.rightCrossing||
        m.rightCrossing-m.leftCrossing!=m.fwhm))throw std::runtime_error("saved bin-center width is inconsistent");
    // Cross-check saved summaries, not a new measurement of the waveform.
    for(const auto& entry:std::vector<std::pair<std::string,double>>{{"hWaveformMeasurementStatusVsCellID",double(status+1)},
       {"hWaveformPeakAmplitudeVsCellID",m.amplitude},{"hWaveformPeakTimeVsCellID",m.peakTime},{"hWaveformFWHMVsCellID",m.fwhm}}) {
      auto* h=dynamic_cast<TH1*>(loaded.file->Get(entry.first.c_str()));if(!h)throw std::runtime_error("missing saved summary: "+entry.first);
      const double saved=h->GetBinContent(h->FindBin(cell));
      const bool unmeasuredNull=entry.first=="hWaveformMeasurementStatusVsCellID"&&status==1&&!profile&&saved==0.;
      if(std::isfinite(entry.second)&&saved!=entry.second&&!unmeasuredNull)throw std::runtime_error("CSV and saved ROOT summary disagree");
    }
    loaded.cells.push_back({cell,profile,m});
  }
  if(!cells.empty())throw std::runtime_error("CSV missing selected cells");
  lfhcal::ValidateWaveformAnnotationCells(loaded.cells);return loaded;
}
void Write(const std::string& manifest,const std::string& database,const std::string& base,lfhcal::WaveformScale scale,const TString& notice="") {
  ValidateDatabase(database);const auto inputs=ReadManifest(manifest);
  const std::string absolute=base+"_Unnormalized.pdf",normalized=base+"_Normalized.pdf";
  for(const auto& p:{absolute,normalized})if(std::filesystem::exists(p))throw std::runtime_error("output exists: "+p);
  std::map<int,Loaded> loaded;for(const auto& item:inputs)loaded.emplace(item.first,Load(item.first,item.second));
  gROOT->SetBatch(true);TCanvas canvas("combined_waveforms","",1600,1350);canvas.SetCanvasSize(1600,1350);
  // Keep the taller canvas within ROOT PDF's fixed A4 MediaBox, including its 20-point margins.
  struct Paper { Float_t x,y; Paper(){gStyle->GetPaperSize(x,y);gStyle->SetPaperSize(23.6,20);} ~Paper(){gStyle->SetPaperSize(x,y);} } paper;
  for(bool norm:{false,true}) {const auto& pdf=norm?normalized:absolute;canvas.Print((pdf+"[").c_str());int page=0;
    for(const auto& group:Groups())for(int run:group.runs) {
      const auto& s=expected.at(run);TString label;
      const int code=s[group.name=="RF"?0:group.name=="CC"?2:group.name=="CF"?1:3];
      const TString identifier=Form("%s = %d",group.name.c_str(),code);
      const TString settings=Form("Settings: RF=%d  CF=%d  CC=%d  CFComp=%d",s[0],s[1],s[2],s[3]);
      if(group.name=="RF")label=Form("RF scan | R = %.5g k#Omega (nominal)",80./s[0]);
      else label=Form("%s scan: %s = %d",group.name.c_str(),group.name.c_str(),s[group.name=="CC"?2:group.name=="CF"?1:3]);
      lfhcal::DrawWaveformGridPage(canvas,loaded.at(run).cells,run,0,true,norm,label,scale,group.color,identifier,settings,++page,26,notice);
      canvas.Print(pdf.c_str());
    }
    canvas.Print((pdf+"]").c_str());
    if(!std::filesystem::exists(pdf)||std::filesystem::file_size(pdf)==0)throw std::runtime_error("failed writing PDF: "+pdf);
  }
}
} // namespace waveform_books
#ifndef WAVEFORM_BOOKS_NO_MAIN
int main(int argc,char** argv) {
  if(argc<4||argc>5){std::cerr<<"Usage: CombineWaveformBooks manifest.csv run_database.csv output_base [isolated|layer|robust|global]\n";return 2;}
  try {std::string option=argc==5?argv[4]:"isolated";auto scale=lfhcal::WaveformScale::IsolatedLayer;
    if(option=="layer")scale=lfhcal::WaveformScale::Layer;else if(option=="robust")scale=lfhcal::WaveformScale::RobustLayer;else if(option=="global")scale=lfhcal::WaveformScale::Global;else if(option!="isolated")throw std::runtime_error("unknown scale");
    waveform_books::Write(argv[1],argv[2],argv[3],scale);
  } catch(const std::exception& e){std::cerr<<"CombineWaveformBooks: "<<e.what()<<'\n';return 1;}return 0;
}
#endif
