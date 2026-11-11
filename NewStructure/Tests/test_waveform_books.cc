#define WAVEFORM_BOOKS_NO_MAIN
#include "../CombineWaveformBooks.cc"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
int main(){
  using namespace waveform_books;
  const auto groups=Groups();size_t pages=0;for(const auto& g:groups)pages+=g.runs.size();
  assert(pages==26);assert(groups[0].runs.front()==345);assert(groups[0].runs.back()==300);
  assert(groups[0].runs[12]==302);assert(groups[2].runs==std::vector<int>({361,355,363,298}));
  assert(Split("1,\"a,b\",\"a\"\"b\"")==Row({"1","a,b","a\"b"}));
  bool rejected=false;try{Split("\"unclosed");}catch(...){rejected=true;}assert(rejected);
  rejected=false;try{Number("nan");}catch(...){rejected=true;}assert(rejected);
  const auto temp=std::filesystem::temp_directory_path()/Form("waveform-book-test-%d",gSystem->GetPid());
  std::filesystem::create_directory(temp);
  std::ofstream manifest(temp/"inputs.csv");manifest<<"run,profile_root,measurements_csv\n";
  for(const auto& r:expected)manifest<<r.first<<",source.root,measurements.csv\n";manifest.close();
  assert(ReadManifest((temp/"inputs.csv").string()).size()==23);
  std::ofstream bad(temp/"bad.csv");bad<<"run,profile_root,measurements_csv\n302,x,y\n302,x,y\n";bad.close();
  rejected=false;try{ReadManifest((temp/"bad.csv").string());}catch(...){rejected=true;}assert(rejected);
  // Full 26+26-page synthetic replay from saved values, with no extraction.
  {
    TFile root((temp/"source.root").c_str(),"RECREATE");
    TH1D status("hWaveformMeasurementStatusVsCellID","",2048,-.5,2047.5);
    TH1D amplitude("hWaveformPeakAmplitudeVsCellID","",2048,-.5,2047.5);
    TH1D time("hWaveformPeakTimeVsCellID","",2048,-.5,2047.5);
    TH1D width("hWaveformFWHMVsCellID","",2048,-.5,2047.5);
    status.SetDirectory(nullptr);amplitude.SetDirectory(nullptr);time.SetDirectory(nullptr);width.SetDirectory(nullptr);
    root.mkdir("IndividualCells");root.cd("IndividualCells");
    for(int base:{1152,1216,1408,1472,1536,1600,1792,1856})for(int i=0;i<8;++i){int cell=base+i;
      if(cell==1863)continue; // Legitimate absent-profile status stays unmeasured (0).
      TProfile p(Form("waveform1DfullCellID%d",cell),"",30,-20,280);
      for(int b=1;b<=30;++b)p.Fill(p.GetBinCenter(b),b==10?100.:b==9||b==11?50.:0.);
      p.Write();status.SetBinContent(cell+1,1);amplitude.SetBinContent(cell+1,100);
      time.SetBinContent(cell+1,75);width.SetBinContent(cell+1,20);
    }
    root.cd();status.Write();amplitude.Write();time.Write();width.Write();root.Close();
  }
  std::ofstream all(temp/"render.csv");all<<"run,profile_root,measurements_csv\n";
  std::ofstream db(temp/"database.csv");db<<"Run Number,RF,CF,CC,CFComp\n";
  for(const auto& entry:expected){int run=entry.first;
    all<<run<<",source.root,"<<run<<".csv\n";db<<run;for(int setting:entry.second)db<<','<<setting;db<<'\n';
    std::ofstream csv(temp/(std::to_string(run)+".csv"));
    csv<<"run,cell,status,has_peak,has_fwhm,peak_bin,left_bin,right_bin,amplitude,peak_time_ns,left_ns,right_ns,fwhm_ns,source\n";
    for(int base:{1152,1216,1408,1472,1536,1600,1792,1856})for(int i=0;i<8;++i)
      if(base+i==1863)csv<<run<<",1863,1,0,0,-1,-1,-1,,,,,,synthetic\n";
      else csv<<run<<','<<base+i<<",0,1,1,10,9,11,100,75,65,85,20,synthetic\n";
  }
  all.close();db.close();
  Write((temp/"render.csv").string(),(temp/"database.csv").string(),(temp/"books").string(),lfhcal::WaveformScale::Layer);
  assert(std::filesystem::file_size(temp/"books_Normalized.pdf")>10000);
  assert(std::filesystem::file_size(temp/"books_Unnormalized.pdf")>10000);
  auto loaded=Load(302,{(temp/"source.root").string(),(temp/"302.csv").string()});
  assert(loaded.cells.front().profile->GetBinContent(10)==100.);
  assert(loaded.cells.front().measurement.amplitude==100.);
  assert(loaded.cells.back().profile==nullptr);
  rejected=false;try{Write((temp/"render.csv").string(),(temp/"database.csv").string(),(temp/"books").string(),lfhcal::WaveformScale::Layer);}catch(...){rejected=true;}assert(rejected);
  // Malformed replay data must not silently create plausible plots.
  std::ifstream original(temp/"302.csv");std::stringstream buffer;buffer<<original.rdbuf();
  const std::string good=buffer.str();
  for(const auto& change:std::vector<std::pair<std::string,std::string>>{
      {",100,75,",",101,75,"},{",10,9,11,",",11,9,11,"},{",0,1,1,",",0,0,1,"}}) {
    std::string changed=good;auto at=changed.find(change.first);assert(at!=std::string::npos);
    changed.replace(at,change.first.size(),change.second);
    std::ofstream altered(temp/"invalid.csv");altered<<changed;altered.close();
    rejected=false;try{Load(302,{(temp/"source.root").string(),(temp/"invalid.csv").string()});}catch(...){rejected=true;}
    assert(rejected);
  }
  std::cout<<"Synthetic PDFs: "<<temp<<'\n';
  // Retain the small synthetic fixture for visual/page-count QA.
std::cout<<"Waveform book grouping, ordering and fail-closed parsing passed\n";
}
