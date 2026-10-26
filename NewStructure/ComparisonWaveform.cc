#include "ComparisonWaveform.h"
#include <vector>
#include "TROOT.h"
#ifdef __APPLE__
#include <unistd.h>
#endif
#include "TF1.h"
#include "TFitResult.h"
#include "TFitResultPtr.h"
#include "TH1D.h"
#include "TH2D.h"
#include "TProfile.h"
#include "TChain.h"
#include "TileSpectra.h"
#include "TileTrend.h"
#include "CalibSummary.h"
#include "MultiCanvas.h"
#include "CommonHelperFunctions.h"
#include "PlotHelper.h"

#include "TBox.h"
#include "TGraph.h"
#include "TGraphErrors.h"
#include "TLatex.h"
#include "TLine.h"
#include "TLegend.h"

#include <array>
#include <cmath>
#include <numeric>

namespace {
enum class AriMetric { PeakAmplitude, FWHM, PeakTime };

struct AriRFSettingData {
  std::vector<std::pair<int,double> > peakAmplitude;
  std::vector<std::pair<int,double> > fwhm;
  std::vector<std::pair<int,double> > peakTime;
  std::array<int,9> statusCounts{};
  int boundaryPeaks = 0;
};

using AriRFData = std::map<double,AriRFSettingData>;

bool IsAriRFCell(int cellID){
  static const int cells[] = {
    1152,1153,1154,1155,1156,1157,1158,1159,
    1216,1217,1218,1219,1220,1221,1222,1223,
    1408,1409,1410,1411,1412,1413,1414,1415,
    1472,1473,1474,1475,1476,1477,1478,1479,
    1536,1537,1538,1539,1540,1541,1542,1543,
    1600,1601,1602,1603,1604,1605,1606,1607,
    1792,1793,1794,1795,1796,1797,1798,1799,
    1856,1857,1858,1859,1860,1861,1862,1863
  };
  return std::find(std::begin(cells),std::end(cells),cellID) != std::end(cells);
}

const std::vector<std::pair<int,double> >& AriValues(const AriRFSettingData& data,
                                                     AriMetric metric){
  if (metric == AriMetric::PeakAmplitude) return data.peakAmplitude;
  if (metric == AriMetric::FWHM) return data.fwhm;
  return data.peakTime;
}

const char* AriMetricName(AriMetric metric){
  if (metric == AriMetric::PeakAmplitude) return "PeakAmplitude";
  if (metric == AriMetric::FWHM) return "FWHM";
  return "PeakTime";
}

const char* AriMetricTitle(AriMetric metric){
  if (metric == AriMetric::PeakAmplitude) return "Peak amplitude (arb. units)";
  if (metric == AriMetric::FWHM) return "FWHM (ns)";
  return "Peak time (ns)";
}

double Quantile(std::vector<double> values, double q){
  std::sort(values.begin(),values.end());
  if (values.empty()) return std::numeric_limits<double>::quiet_NaN();
  if (values.size() == 1) return values.front();
  const double position = q*(values.size()-1);
  const size_t low = static_cast<size_t>(std::floor(position));
  const size_t high = static_cast<size_t>(std::ceil(position));
  const double fraction = position-low;
  return values[low]*(1.-fraction)+values[high]*fraction;
}

std::vector<double> PlainValues(const std::vector<std::pair<int,double> >& values){
  std::vector<double> result;
  result.reserve(values.size());
  for (const auto& value : values) result.push_back(value.second);
  return result;
}

void DrawAriBoxes(const AriRFData& data, AriMetric metric){
  const int nSettings = static_cast<int>(data.size());
  double yMin = std::numeric_limits<double>::infinity();
  double yMax = -std::numeric_limits<double>::infinity();
  for (const auto& setting : data){
    for (const auto& value : AriValues(setting.second,metric)){
      yMin = std::min(yMin,value.second);
      yMax = std::max(yMax,value.second);
    }
  }
  if (!std::isfinite(yMin) || !std::isfinite(yMax)){
    yMin = 0.;
    yMax = 1.;
  } else if (!(yMax > yMin)){
    const double padding = std::max(1.,0.1*std::fabs(yMin));
    yMin -= padding;
    yMax += padding;
  }
  const double span = yMax-yMin;
  yMin -= 0.08*span;
  yMax += 0.12*span;
  if (metric != AriMetric::PeakTime && yMin > 0.) yMin = 0.;

  TH1D* frame = new TH1D(Form("hAri%sRFFrame",AriMetricName(metric)),
                          Form("Ari %s by RF;RF (k#Omega);%s",
                               AriMetricName(metric),AriMetricTitle(metric)),
                          nSettings,0.5,nSettings+0.5);
  frame->SetDirectory(nullptr);
  frame->SetStats(0);
  frame->SetMinimum(yMin);
  frame->SetMaximum(yMax);

  int settingIndex = 0;
  for (const auto& setting : data){
    ++settingIndex;
    frame->GetXaxis()->SetBinLabel(settingIndex,Form("%.3g",setting.first));
  }
  frame->Draw("AXIS");

  settingIndex = 0;
  for (const auto& setting : data){
    ++settingIndex;
    const auto& channelValues = AriValues(setting.second,metric);
    if (channelValues.empty()) continue;
    const std::vector<double> values = PlainValues(channelValues);

    TGraph* points = new TGraph();
    for (size_t i = 0; i < channelValues.size(); ++i){
      const double jitter = 0.18*std::sin(0.37*channelValues[i].first);
      points->SetPoint(static_cast<int>(i),settingIndex+jitter,channelValues[i].second);
    }
    points->SetName(Form("gAri%sRF%.4gAllChannels",AriMetricName(metric),setting.first));
    points->SetMarkerStyle(20);
    points->SetMarkerSize(0.45);
    points->SetMarkerColorAlpha(kGray+2,0.40);
    points->Draw("P SAME");

    const double q1 = Quantile(values,0.25);
    const double median = Quantile(values,0.50);
    const double q3 = Quantile(values,0.75);
    const auto minmax = std::minmax_element(values.begin(),values.end());
    const double x = settingIndex;
    const double boxWidth = 0.27;
    TBox* box = new TBox(x-boxWidth,q1,x+boxWidth,q3);
    box->SetFillColorAlpha(kAzure-9,0.45);
    box->SetLineColor(kBlue+2);
    box->SetLineWidth(2);
    box->Draw("same");
    TLine* medianLine = new TLine(x-boxWidth,median,x+boxWidth,median);
    medianLine->SetLineWidth(3);
    medianLine->Draw("same");
    TLine* lowStem = new TLine(x,*minmax.first,x,q1);
    TLine* highStem = new TLine(x,q3,x,*minmax.second);
    TLine* lowCap = new TLine(x-0.12,*minmax.first,x+0.12,*minmax.first);
    TLine* highCap = new TLine(x-0.12,*minmax.second,x+0.12,*minmax.second);
    lowStem->Draw("same"); highStem->Draw("same");
    lowCap->Draw("same"); highCap->Draw("same");
  }

  TLatex* note = new TLatex();
  note->SetNDC();
  note->SetTextSize(0.030);
  note->SetTextColor(kGray+2);
  note->DrawLatex(0.12,0.92,
    "points = all valid channels; box = IQR; whiskers = full valid range; line = median");
}

void DrawAriSummary(const AriRFData& data, AriMetric metric, TFile* output){
  TGraphErrors* mean = new TGraphErrors();
  TGraph* median = new TGraph();
  mean->SetName(Form("gAri%sRFMeanCellSpread",AriMetricName(metric)));
  median->SetName(Form("gAri%sRFMedian",AriMetricName(metric)));
  int point = 0;
  for (const auto& setting : data){
    const std::vector<double> values = PlainValues(AriValues(setting.second,metric));
    if (values.empty()) continue;
    const double average = std::accumulate(values.begin(),values.end(),0.)/values.size();
    double sumSquares = 0.;
    for (double value : values) sumSquares += (value-average)*(value-average);
    const double spread = values.size() > 1 ? std::sqrt(sumSquares/(values.size()-1)) : 0.;
    mean->SetPoint(point,setting.first,average);
    mean->SetPointError(point,0.,spread);
    median->SetPoint(point,setting.first,Quantile(values,0.5));
    ++point;
  }
  mean->SetTitle(Form("Ari %s vs RF;RF (k#Omega);%s",
                      AriMetricName(metric),AriMetricTitle(metric)));
  mean->SetMarkerStyle(20);
  mean->SetLineWidth(2);
  mean->SetLineColor(kBlue+2);
  mean->SetMarkerColor(kBlue+2);
  mean->Draw("AP");
  median->SetMarkerStyle(24);
  median->SetLineWidth(2);
  median->Draw("LP SAME");
  TLegend* legend = new TLegend(0.55,0.74,0.88,0.88);
  legend->SetBorderSize(0);
  legend->SetFillStyle(0);
  legend->AddEntry(mean,"mean #pm channel-to-channel SD","lp");
  legend->AddEntry(median,"median","lp");
  legend->Draw();
  if (output){
    output->cd();
    mean->Write();
    median->Write();
  }
}

void PlotAriRFScan(const AriRFData& data, const TString& outputDirectory,
                   const TString& suffix, TFile* output){
  if (data.empty()) return;
  TCanvas* canvas = new TCanvas("canvasAriRFMeasurements","",0,0,1450,1300);
  canvas->Divide(1,3,0.001,0.001);
  canvas->cd(1); gPad->SetGridy(); DrawAriBoxes(data,AriMetric::PeakAmplitude);
  canvas->cd(2); gPad->SetGridy(); DrawAriBoxes(data,AriMetric::FWHM);
  canvas->cd(3); gPad->SetGridy(); DrawAriBoxes(data,AriMetric::PeakTime);
  canvas->SaveAs(Form("%s/AriRF_WaveformMeasurements.%s",outputDirectory.Data(),suffix.Data()));
  if (output){
    output->cd();
    canvas->Write("canvasAriRFWaveformMeasurements");
  }

  canvas->Clear();
  canvas->Divide(1,3,0.001,0.001);
  canvas->cd(1); gPad->SetGrid(); DrawAriSummary(data,AriMetric::PeakAmplitude,output);
  canvas->cd(2); gPad->SetGrid(); DrawAriSummary(data,AriMetric::FWHM,output);
  canvas->cd(3); gPad->SetGrid(); DrawAriSummary(data,AriMetric::PeakTime,output);
  canvas->SaveAs(Form("%s/AriRF_WaveformSummary.%s",outputDirectory.Data(),suffix.Data()));
  if (output){
    output->cd();
    canvas->Write("canvasAriRFWaveformSummary");
  }

  TH2D* status = new TH2D("hAriRFWaveformMeasurementStatus",
                          "Ari RF waveform extraction status;RF (k#Omega);status;channels",
                          data.size(),0.5,data.size()+0.5,10,-0.5,9.5);
  int settingIndex = 0;
  for (const auto& setting : data){
    ++settingIndex;
    status->GetXaxis()->SetBinLabel(settingIndex,Form("%.3g",setting.first));
    for (int code = 0; code <= 8; ++code)
      status->SetBinContent(settingIndex,code+1,setting.second.statusCounts[code]);
    status->SetBinContent(settingIndex,10,setting.second.boundaryPeaks);
  }
  for (int code = 0; code <= 8; ++code)
    status->GetYaxis()->SetBinLabel(code+1,TileSpectra::WaveformMeasurementStatusName(
      static_cast<WaveformMeasurementStatus>(code)));
  status->GetYaxis()->SetBinLabel(10,"peak at boundary");
  canvas->Clear();
  status->SetStats(0);
  status->Draw("COLZ TEXT");
  canvas->SaveAs(Form("%s/AriRF_WaveformStatus.%s",outputDirectory.Data(),suffix.Data()));
  if (output){
    output->cd();
    status->Write();
  }
}
}


// ===========================================================================================
// Check input files and global settings
// ===========================================================================================
bool ComparisonWaveform::CheckAndOpenIO(void){
  
  int matchingbranch;
  
  // *****************************************************************************************
  // Reading files from a text file
  // *****************************************************************************************
  if(!InputListName.IsNull()){
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    // text file with 2 files per line 1 full file & 1 histo file
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    std::cout << "You need to provide data tree file with the setup & calib from the injection runs & a histo file" << std::endl;
    std::fstream dummyTxt;
    dummyTxt.open(InputListName.Data(),std::ios::in);
    if(!dummyTxt.is_open()){
      std::cout<<"Error opening "<<InputListName.Data()<<", does the file exist?"<<std::endl;
    }
    std::string dummyRootCalibName;
    std::string dummyRootHistName;
    // set first root file names
    dummyTxt>>dummyRootCalibName >> dummyRootHistName;
    
    int goodcalib;
    int goodsetup;
    while(dummyTxt.good()){
      std::cout << dummyRootCalibName.data() << "\t" << dummyRootHistName.data() << std::endl;
      
      // check that files exist and can be opened
      TFile dummyRootCalib=TFile(dummyRootCalibName.c_str(),"READ");
      if(dummyRootCalib.IsZombie()){
        std::cout<<"Error opening '"<<dummyRootCalibName<<", does the file exist?"<<std::endl;
        return false;
      }
      dummyRootCalib.Close();
      TFile dummyRootHist=TFile(dummyRootHistName.c_str(),"READ");
      if(dummyRootHist.IsZombie()){
        std::cout<<"Error opening '"<<dummyRootHistName<<", does the file exist?"<<std::endl;
        return false;
      }
      dummyRootHist.Close();
      
      // Add file-name to setup and calib chain as well string-vector
      AddInputFile(dummyRootHistName);
      goodsetup=TsetupIn->AddFile(dummyRootCalibName.c_str());
      goodcalib=TcalibIn->AddFile(dummyRootCalibName.c_str());
      if(goodcalib==0){
          std::cout<<"Issues retrieving Calib tree from "<<dummyRootCalibName<<", file is ignored"<<std::endl;
        }
      if(goodsetup==0){
        std::cout<<"Issues retrieving Setup tree from "<<dummyRootCalibName<<", file is ignored"<<std::endl;
      }
      // set next root file names
      dummyTxt>>dummyRootCalibName >> dummyRootHistName;
    }
  }
  // *****************************************************************************************
  // Setup Output files
  // *****************************************************************************************
  if(RootOutputName.IsNull()){
    return false;
  } else {
    if(!CreateOutputRootFile()){
      return false;
    }
  }

  // *****************************************************************************************
  // Setup TChain of setups and calibrations
  // *****************************************************************************************
  // intialize global variable setup
  setup=Setup::GetInstance();
  std::cout<<"Setup add "<<setup<<std::endl;
  matchingbranch=TsetupIn->SetBranchAddress("setup",&rswptr);
  if(matchingbranch<0){
    std::cout<<"Error retrieving Setup info from the tree"<<std::endl;
    return false;
  }
  std::cout<<"Entries "<<TsetupIn->GetEntries()<<std::endl;
  TsetupIn->GetEntry(0);
  setup->Initialize(*rswptr);
  // initialize calib with the correct branch
  matchingbranch=TcalibIn->SetBranchAddress("calib",&calibptr);
  if(matchingbranch<0){
    std::cout<<"Error retrieving calibration info from the tree"<<std::endl;
    return false;
  }
  
  return true;    
}

// ===========================================================================================
// Main function of this calibration comparison 
// ===========================================================================================
bool ComparisonWaveform::ProcessWaveformCompare(void){
  // *****************************************************************************************
  // plotting settings
  // *****************************************************************************************
  gSystem->Exec("mkdir -p "+OutputNameDirPlots);
  if (ExtPlot > 0) gSystem->Exec("mkdir -p "+OutputNameDirPlots+"/SingleLayer");
  StyleSettingsBasics("pdf");
  SetPlotStyle();  

  // *****************************************************************************************
  // Some general setup
  // *****************************************************************************************
  bool status=true;
  // enbale implitcit root multithreading
  ROOT::EnableImplicitMT();
  // get nuber of entires from Calib tree (how many runs do we have)
  int entries=TcalibIn->GetEntries();
  std::cout << "Entries in calib tree: " << entries << std::endl;
  
  // *****************************************************************************************
  // global variable setup, common iterators and ranges
  // ******************************************************************************************
  std::map<int, TileTrend> trend;
  std::map<int, TileTrend>::iterator itrend;
  std::map<int, TileCalib>::const_iterator itcalib;

  std::map<int, CalibSummary> sumCalibs;
  std::map<int, CalibSummary>::iterator isumCalibs;
  AriRFData ariRFData;
  
  double Xvalue;
  double Xmin= 9999.;
  double Xmax=-9999.;
  int nRun = 0;
  
  // ******************************************************************************************
  // ************* Get run data base to potentially obtain more information from file *********
  // ******************************************************************************************
  std::map<int,RunInfo> ri=readRunInfosFromFile(RunListInputName.Data(),debug,0);
  std::map<int,RunInfo>::iterator itRun; // basic infos
  int firstRunNr    = -1;
  
  std::vector<RunInfo> runList;
  
  // ******************************************************************************************
  // Iterate over all entries (runs) in the calib tree
  // ******************************************************************************************
  for(int ientry=0; ientry<entries;ientry++){
    TsetupIn->GetEntry(ientry);
    TcalibIn->GetEntry(ientry);
    
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    // set global iterator for runs to first run number in list to obtain beam-line, dates...
    if (ientry==0) firstRunNr = calib.GetRunNumber();
    itRun = ri.find(calib.GetRunNumber());
    runList.push_back(itRun->second);
    double set_rf     = (double)itRun->second.rf;
    double set_cf     = (double)itRun->second.cf;
    double set_cc     = (double)itRun->second.cc;
    double set_cfcomp = (double)itRun->second.cfcomp;
    double set_injec  = -10000.;
    std::cout <<calib.GetRunNumber() << "\t" << set_rf << "\t" << set_cf << "\t" << set_cc << "\t" << set_cfcomp << "\t" << set_injec<< std::endl;
    if (ariRFScan){
      AriRFSettingData& rfData = ariRFData[ReturnRFValue(itRun->second.rf)];
      rfData.statusCounts[static_cast<int>(WaveformMeasurementStatus::NullProfile)] += 64;
    }
    
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    // Set X-values according to option
    // Xaxis:   
    //        0 - Run number dependence
    //        1 - Operational Voltage dependence
    //        2 - Time dependence
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    Int_t runNumber = calib.GetRunNumber();
    Xvalue=calib.GetRunNumber();
    if(Xvalue<Xmin) Xmin=Xvalue;
    if(Xvalue>Xmax) Xmax=Xvalue;

    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    // Initialize calib summary
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    calib.PrintGlobalInfo();
    CalibSummary aSum = CalibSummary(nRun, runNumber,calib.GetVop(), 0);
    aSum.SetRunProperties(itRun->second);
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    // Reading additional summary histos from 2nd file
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    TFile* tempFile = nullptr;    
    if (nRun < (int)RootInputNames.size()){
      std::cout << "reading hist file: " <<RootInputNames[nRun].Data() << " expanded list setting: " << expandedList << std::endl;
      tempFile      = new TFile(RootInputNames[nRun].Data(),"READ");
    }
    
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    // Loop over all cells in the calib object for trending plots
    // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    for(itcalib=calib.begin(); itcalib!=calib.end(); ++itcalib){

      // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
      // Reading additional cell histos from 2nd file
      // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%      
      TProfile* profCellWave= nullptr;
      TH1D* histCellTOA= nullptr;
      TH1D* histCellTOT= nullptr;
      
      // std::cout << "celld id: " << itcalib->first << "\t "<< calib.GetPedestalMeanH(itcalib->first);
      // reading Waveform
      profCellWave     = (TProfile*)tempFile->Get(Form("IndividualCells/waveform1DfullCellID%i",itcalib->first));
      // reading ToA
      histCellTOA      = (TH1D*)tempFile->Get(Form("IndividualCells/hspectrafullTOACellID%i",itcalib->first));
      // reading ToT
      histCellTOT      = (TH1D*)tempFile->Get(Form("IndividualCells/hspectrafullTOTCellID%i",itcalib->first));
      // std::cout <<"\t Wave: "<< profCellWave << "\t TOA: " << histCellTOA << "\t TOT " << histCellTOT << std::endl;
      int entries = 0;
      if (profCellWave)
        entries = profCellWave->GetEntries();
      if (ariRFScan && IsAriRFCell(itcalib->first)){
        AriRFSettingData& rfData = ariRFData[ReturnRFValue(itRun->second.rf)];
        --rfData.statusCounts[static_cast<int>(WaveformMeasurementStatus::NullProfile)];
        const WaveformMeasurement measurement = TileSpectra::MeasureWaveform(profCellWave);
        const int statusCode = static_cast<int>(measurement.status);
        if (statusCode >= 0 && statusCode < static_cast<int>(rfData.statusCounts.size()))
          ++rfData.statusCounts[statusCode];
        if (measurement.peakAtSearchBoundary) ++rfData.boundaryPeaks;
        if (measurement.hasPeak){
          rfData.peakAmplitude.push_back({itcalib->first,measurement.amplitude});
          rfData.peakTime.push_back({itcalib->first,measurement.peakTime});
        }
        if (measurement.hasFWHM)
          rfData.fwhm.push_back({itcalib->first,measurement.fwhm});
      }
      if (entries == 0) continue;
      // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
      // fill calib summary object for specific cell
      // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
      aSum.Fill(itcalib->second);
      
      // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
      // fill trending object for a single cell
      // %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
      // check if iterator points to end of map
      itrend=trend.find(itcalib->first);
      if(itrend!=trend.end()){
        // fill injection hists
        itrend->second.Fill(Xvalue,itcalib->second, (int)calib.GetRunNumber(), (double)calib.GetVop(),itRun->second.pdg, -10000., -10000.,itRun->second.energy,itRun->second.temp);
        itrend->second.FillExtended(Xvalue,profCellWave->GetEntries(), (int)calib.GetRunNumber(), histCellTOT, histCellTOA, nullptr, profCellWave);
        itrend->second.FillHGCROCSetting (set_rf, set_cf, set_cfcomp, set_cc, set_injec);
      // create new TileTrend object if not yet available in map
      } else {
        TileTrend atrend=TileTrend(itcalib->first,0, 2);
        // fill injection hists
        atrend.Fill(Xvalue,itcalib->second, (int)calib.GetRunNumber(), (double)calib.GetVop(), itRun->second.pdg, -10000., -10000.,itRun->second.energy,itRun->second.temp );
        atrend.FillExtended(Xvalue,profCellWave->GetEntries(), (int)calib.GetRunNumber(),histCellTOT,  histCellTOA, nullptr, profCellWave);
        atrend.FillHGCROCSetting (set_rf, set_cf, set_cfcomp, set_cc, set_injec);
        // append TileTrend object to map
        trend[itcalib->first]=atrend;
      }
    } // end loop over cells in the calib object
    
    // append CalibSummary object to map
    sumCalibs[nRun]=aSum;
    // close additional files opened
    if (expandedList){
      tempFile->Close(); 
    }
    // increase run-counter
    nRun++;
  } // end loop over entries (runs) in calib tree
  
  // ******************************************************************************************
  // Print summary of calib runs
  // ******************************************************************************************    
  std::cout << "Calibs summary: "<< sumCalibs.size() << std::endl;
  int globalStatus = 0;
  for(isumCalibs=sumCalibs.begin(); isumCalibs!=sumCalibs.end(); ++isumCalibs){
    int calibstatus = isumCalibs->second.Analyse(debug);
    if (globalStatus < calibstatus) globalStatus = calibstatus;
  }
  std::cout << "Global calib status: " << globalStatus << std::endl;
  
  if (globalStatus == 0){
    std::cout << "!!!!!!!!!!!!!!!!!!!!!  ATTENTION !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" << std::endl;
    std::cout << "Aborting plotting: none of the files has either ped or mip scales filled" << std::endl; 
  }
  
  
  // ******************************************************************************************
  // Extract common run infos
  // ******************************************************************************************
  RunInfo commonRunInfo = GetCommonRunInfoFromList(runList);
  PrintSettingsRunInfo(commonRunInfo);
  int labelOpt        = 1;
  Int_t nSameSettings = GetNSameSettings(commonRunInfo, labelOpt);

  // ******************************************************************************************
  // Set X axis title and ranges 
  // ******************************************************************************************
  if (Xaxis == 0){
    Xmin= Xmin-10;
    Xmax= Xmax+10;
  } 

  TString             xaxisTitle = "";
  if (Xaxis==0)       xaxisTitle = "Run Nr. ";
  
  for(itrend=trend.begin(); itrend!=trend.end(); ++itrend){    
    // sort graphs
    itrend->second.Sort();
    // set x axis title for trending graphs
    itrend->second.SetXAxisTitle(xaxisTitle);
    // write graphs for each cell to output
    itrend->second.Write(RootOutput);
    for (int i = 0; i <itrend->second.GetNRuns(); i++ ){
      if (Xaxis == 3){
        itrend->second.SetLabelPerRun(Form("it. %d", i));
      } else if (Xaxis == 4){
        itrend->second.SetLabelPerRun(Form("int. %d", i));
      } else {
        itrend->second.SetLabelPerRun(itrend->second.GetLabelLegend( commonRunInfo, i, nSameSettings));
      }
      // std::cout << i << "\t Run: "<<itrend->second.GetRunNr(i) << "\t Label: " << itrend->second.GetLabel(i) << std::endl;     
    }
  }

  int cCalib = 0;
  for (isumCalibs = sumCalibs.begin(); isumCalibs!=sumCalibs.end(); ++isumCalibs){
    if (Xaxis == 3){
      isumCalibs->second.SetLabel(Form("it. %d", cCalib));
    } else if (Xaxis == 4){
      isumCalibs->second.SetLabel(Form("int. %d", cCalib));
    } else {
      isumCalibs->second.SetLabel(isumCalibs->second.GetLabelLegend( commonRunInfo,  nSameSettings));
    }
    // std::cout << cCalib << "\t Run: "<<isumCalibs->second.GetRunNumber() << "\t Label: " << isumCalibs->second.GetLabel() << std::endl;     
    cCalib++;
  }

  
  //******************************************************************************
  // plotting overview for each run overlayed
  //******************************************************************************
  Int_t textSizePixel   = 30;
  Float_t textSizeRel   = 0.04;  
  TCanvas* canvas1DRunsOverlay = new TCanvas("canvas1DRunsOverlay","",0,0,1450,1300);  // gives the page size
  DefaultCanvasSettings( canvas1DRunsOverlay, 0.075, 0.015, 0.025, 0.09);

  PlotCalibRunOverlay( canvas1DRunsOverlay, 0, sumCalibs, textSizeRel, 
                      Form("%s/HGPedSummary_RunOverlay.%s",OutputNameDirPlots.Data(),plotSuffix.Data()), commonRunInfo,"", debug);
  PlotCalibRunOverlay( canvas1DRunsOverlay, 1, sumCalibs, textSizeRel, 
                      Form("%s/HGPedWidthSummary_RunOverlay.%s",OutputNameDirPlots.Data(),plotSuffix.Data()), commonRunInfo,"", debug);

  if (ariRFScan)
    PlotAriRFScan(ariRFData,OutputNameDirPlots,plotSuffix,RootOutput);
  
  // plotting individual layers/asics
  DetConf::Type detConf = DetConf::Type::Asic;
  // DetConf::Type detConf = DetConf::Type::Single8M;
  // DetConf::Type detConf = DetConf::Type::Dual8M;
  MultiCanvas panelPlot2D(detConf, "Waveform");
  bool init2D = panelPlot2D.Initialize(2);
  
  // panelPlot2D.PlotTrending(trend, 0, Xmin,Xmax, OutputNameDirPlots, "PedADC", plotSuffix, commonRunInfo, ExtPlot );
  panelPlot2D.PlotRunOverlayProfile(trend, nRun, 1, -25, 25*commonRunInfo.samples, -10, -10000, OutputNameDirPlots, "WaveOverlay", plotSuffix, commonRunInfo, ExtPlot );
  // panelPlot2D.PlotRunOverlayProfile(trend, nRun, 3, 0, 18*7, 0,-10000, OutputNameDirPlots, "TOTOverlay", plotSuffix, commonRunInfo, ExtPlot );
  // panelPlot2D.PlotRunOverlayProfile(trend, nRun, 2, 0, 18*7, 0,1024, OutputNameDirPlots, "TOAOverlay", plotSuffix, commonRunInfo, ExtPlot );

  std::vector <int> cellVec;
  if (cellList.CompareTo("")!= 0){
    std::cout << "cell List set: "  << cellList.Data() << std::endl;
    std::fstream cellTxt;
    cellTxt.open(cellList.Data(),std::ios::in);
    if(!cellTxt.is_open()){
      std::cout<<"Error opening "<<cellList.Data()<<", does the file exist?"<<std::endl;
    }
    while(cellTxt.good()){
      TString dummyCell;
      // set first root file names
      cellTxt>>dummyCell;
      std::cout << "\t" << dummyCell.Data() << std::endl;
      if (dummyCell.CompareTo("") != 0)
        cellVec.push_back(dummyCell.Atoi());
    }
    std::cout << "registered: " << cellVec.size() << " single cells to be plotted" << std::endl;
    for (int i = 0; i < cellVec.size(); i++){
        std::cout << cellVec.at(i) << "," ;
    }
    std::cout << std::endl;
  }
  
  if (cellVec.size() > 0){
    
    detConf = DetConf::Type::SingleTile;
    MultiCanvas panelSingleTile(detConf, "WaveformTile");
    panelSingleTile.SetCellVector(cellVec);
    bool initSngle = panelSingleTile.Initialize(1);
    panelSingleTile.SetLabelOpt(1);
    
    panelSingleTile.PlotRunOverlayProfile(trend, nRun, 1, -25, 25*commonRunInfo.samples, -10, 1324, OutputNameDirPlots, "TileWaveOverlay", plotSuffix, commonRunInfo, ExtPlot);
    panelSingleTile.PlotRunOverlaySpectra(trend, nRun, 0, 0, 4148, OutputNameDirPlots, "TileTOTSpectra", plotSuffix, commonRunInfo, ExtPlot, debug, 0);
    panelSingleTile.PlotRunOverlaySpectra(trend, nRun, 1, 0, 1024, OutputNameDirPlots, "TileTOASpectra", plotSuffix, commonRunInfo, ExtPlot, debug, 0);
    
  }
  return status;
}


// ===========================================================================================
// Create the output file 
// ===========================================================================================
bool ComparisonWaveform::CreateOutputRootFile(void){

  std::string testing = RootOutputName.Data();
  std::size_t found = testing.find_last_of("/\\");
  std::cout << " path: " << testing.substr(0,found) << '\n';
  std::cout << " file: " << testing.substr(found+1) << '\n';
  std::string path = testing.substr(0,found);
  if (path.size() > 0){
    std::cout << "Checking whether directory needs to be created: " << path.data() << std::endl;
    gSystem->Exec(Form("mkdir -p %s",path.data()));
  }

  if(Overwrite){
    RootOutput=new TFile(RootOutputName.Data(),"RECREATE");
  } else{
    RootOutput = new TFile(RootOutputName.Data(),"CREATE");
  }
  if(RootOutput->IsZombie()){
    std::cout<<"Error opening '"<<RootOutput<<"'no reachable path? Exist without force mode to overwrite?..."<<std::endl;
    return false;
  }
  return true;
}
