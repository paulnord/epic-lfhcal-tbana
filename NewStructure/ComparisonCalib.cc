#include "ComparisonCalib.h"
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
#include "CommonHelperFunctions.h"
#include "PlottHelper.h"

bool ComparisonCalib::CheckAndOpenIO(void){
  int matchingbranch;
  
  std::cout<< __LINE__ << std::endl;
  if(!InputListName.IsNull()){
    if (!expandedList){
      std::cout << "*********************************************************" << std::endl;
      std::cout << "Simple reading from file list" << std::endl;
      std::cout << "*********************************************************" << std::endl;
      //File exist?
      std::cout << "reading from file list: " << InputListName.Data() << std::endl;
      std::fstream dummyTxt;
      dummyTxt.open(InputListName.Data(),std::ios::in);
      if(!dummyTxt.is_open()){
        std::cout<<"Error opening "<<InputListName.Data()<<", does the file exist?"<<std::endl;
      }
      std::string dummyRootName;
      dummyTxt>>dummyRootName;
      int goodsetup;
      int goodcalib;
      while(dummyTxt.good()){
        std::cout << dummyRootName.data() << std::endl;
        TFile dummyRoot=TFile(dummyRootName.c_str(),"READ");
        if(dummyRoot.IsZombie()){
          std::cout<<"Error opening '"<<dummyRootName<<", does the file exist?"<<std::endl;
          return false;
        }
        dummyRoot.Close();
        goodsetup=TsetupIn->AddFile(dummyRootName.c_str());
        goodcalib=TcalibIn->AddFile(dummyRootName.c_str());
        if(goodcalib==0){
          std::cout<<"Issues retrieving Calib tree from "<<dummyRootName<<", file is ignored"<<std::endl;
        }
        if(goodsetup==0){
          std::cout<<"Issues retrieving Setup tree from "<<dummyRootName<<", file is ignored"<<std::endl;
        }
        dummyTxt>>dummyRootName;
      }
    } else {  // read more complex files
      std::cout << "You need to provide a calib file and an output of the improved muon calib in the textfile in each line" << std::endl;
      std::fstream dummyTxt;
      dummyTxt.open(InputListName.Data(),std::ios::in);
      if(!dummyTxt.is_open()){
        std::cout<<"Error opening "<<InputListName.Data()<<", does the file exist?"<<std::endl;
      }
      std::string dummyRootCalibName;
      std::string dummyRootHistName;
      dummyTxt>>dummyRootCalibName >> dummyRootHistName;
      int goodsetup;
      int goodcalib;
      while(dummyTxt.good()){
        std::cout << dummyRootCalibName.data() << "\t" << dummyRootHistName.data() << std::endl;
        TFile dummyRootCalib=TFile(dummyRootCalibName.c_str(),"READ");
        if(dummyRootCalib.IsZombie()){
          std::cout<<"Error opening '"<<dummyRootCalibName<<", does the file exist?"<<std::endl;
          return false;
        }
        TFile dummyRootHist=TFile(dummyRootHistName.c_str(),"READ");
        if(dummyRootHist.IsZombie()){
          std::cout<<"Error opening '"<<dummyRootHistName<<", does the file exist?"<<std::endl;
          return false;
        }
        dummyRootCalib.Close();
        goodsetup=TsetupIn->AddFile(dummyRootCalibName.c_str());
        goodcalib=TcalibIn->AddFile(dummyRootCalibName.c_str());
        if(goodcalib==0){
          std::cout<<"Issues retrieving Calib tree from "<<dummyRootCalibName<<", file is ignored"<<std::endl;
        }
        if(goodsetup==0){
          std::cout<<"Issues retrieving Setup tree from "<<dummyRootCalibName<<", file is ignored"<<std::endl;
        }
        dummyTxt>>dummyRootCalibName >> dummyRootHistName;
      }
    }
  }
  else {//we did not provide a txt file with a list of root file we want to process but directly the list of files to process
    std::cout << "*********************************************************" << std::endl;
    std::cout << "Simple reading from vector" << std::endl;
    std::cout << "*********************************************************" << std::endl;
    
    if(RootInputNames.empty()){
      std::cout<<"No root files, neither text list file provided"<<std::endl;
      return false;
    }
    std::vector<TString>::iterator it;
    int goodsetup;
    int goodcalib;
    for(it=RootInputNames.begin(); it!=RootInputNames.end(); ++it){
      TFile dummy=TFile(it->Data(),"READ");
      if(dummy.IsZombie()){
        std::cout<<"Error opening '"<<it->Data()<<", does the file exist?"<<std::endl;
        return false;
      }
      dummy.Close();
      goodsetup=TsetupIn->AddFile(it->Data());
      goodcalib=TcalibIn->AddFile(it->Data());
      if(goodcalib==0){
        std::cout<<"Issues retrieving Calib tree from "<<it->Data()<<", file is ignored"<<std::endl;
      }
      if(goodsetup==0){
        std::cout<<"Issues retrieving Setup tree from "<<it->Data()<<", file is ignored"<<std::endl;
      }
    }
  }
  //Setup Output files
  if(RootOutputName.IsNull()){
    return false;
  }
  else{
    if(!CreateOutputRootFile()){
      return false;
    }
  }
  

  //If we are still here, we should be able to initalise the address of TChain to get to the setup and the calib
  
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


  matchingbranch=TcalibIn->SetBranchAddress("calib",&calibptr);
  if(matchingbranch<0){
    std::cout<<"Error retrieving calibration info from the tree"<<std::endl;
    return false;
  }
  return true;    
}


bool ComparisonCalib::Process(void){
  
  // plotting settings
  gSystem->Exec("mkdir -p "+OutputNameDirPlots);
  StyleSettingsBasics("pdf");
  SetPlotStyle();  

  bool status=true;
  ROOT::EnableImplicitMT();
  int entries=TcalibIn->GetEntries();


  std::map<int, TileTrend> trend;
  std::map<int, TileTrend>::iterator itrend;
  std::map<int, TileCalib>::const_iterator itcalib;

  std::map<int, CalibSummary> sumCalibs;
  std::map<int, CalibSummary>::iterator isumCalibs;
  
  double Xvalue;
  double Xmin= 9999.;
  double Xmax=-9999.;
  for(int ientry=0; ientry<entries;ientry++){
    TcalibIn->GetEntry(ientry);
    TsetupIn->GetEntry(ientry);
    //So far same values for all tiles, otherwise should be moved inside the for loop below
    if(Xaxis==0){//depending on run #
      Xvalue=calib.GetRunNumber();
    }
    else if(Xaxis==1){
      Xvalue=calib.GetVop();
    }
    else if(Xaxis==2){
      Xvalue=calib.GetBeginRunTime()->GetSec();
    }
    CalibSummary aSum = CalibSummary(calib.GetRunNumber());
    if(Xvalue<Xmin) Xmin=Xvalue;
    if(Xvalue>Xmax) Xmax=Xvalue;
    for(itcalib=calib.begin(); itcalib!=calib.end(); ++itcalib){
      itrend=trend.find(itcalib->first);
      aSum.Fill(itcalib->second);
      if(itrend!=trend.end()){
        itrend->second.Fill(Xvalue,itcalib->second, (int)calib.GetRunNumber());
      } else {
        TileTrend atrend=TileTrend(itcalib->first,0);
        atrend.Fill(Xvalue,itcalib->second, (int)calib.GetRunNumber());
        trend[itcalib->first]=atrend;
      }
    }
    sumCalibs[calib.GetRunNumber()]=aSum;
  }
  std::cout << "Calibs summary: "<< sumCalibs.size() << std::endl;
  
  if (Xaxis == 0){
    Xmin= Xmin-10;
    Xmax= Xmax+10;
  } else if (Xaxis == 1){
    Xmin= Xmin-0.5;
    Xmax= Xmax+0.5;
  } 
  
  double MaxLGped    =0.;
  double MaxHGped    =0.;
  double MaxLGscale  =0.;
  double MaxHGscale  =0.;
  double MaxHGLGcorr =0.;
  double MaxLGHGcorr =0.;
  
  double MinLGped    =9999.;
  double MinHGped    =9999.;
  double MinLGscale  =9999.;
  double MinHGscale  =9999.;
  double MinHGLGcorr =9999.;
  double MinLGHGcorr =9999.;

  TString xaxisTitle = "";
  if (Xaxis==0) xaxisTitle = "Run Nr. ";
  else if (Xaxis==1) xaxisTitle = "V (V) ";
  else xaxisTitle = "date";  
  
  for(itrend=trend.begin(); itrend!=trend.end(); ++itrend){
    if(MinLGped>itrend->second.GetMinLGped()) MinLGped=itrend->second.GetMinLGped();
    if(MaxLGped<itrend->second.GetMaxLGped()) MaxLGped=itrend->second.GetMaxLGped();
    if(MinHGped>itrend->second.GetMinHGped()) MinHGped=itrend->second.GetMinHGped();
    if(MaxHGped<itrend->second.GetMaxHGped()) MaxHGped=itrend->second.GetMaxHGped();
    
    if(MinLGscale>itrend->second.GetMinLGscale()) MinLGscale=itrend->second.GetMinLGscale();
    if(MaxLGscale<itrend->second.GetMaxLGscale()) MaxLGscale=itrend->second.GetMaxLGscale();
    if(MinHGscale>itrend->second.GetMinHGscale()) MinHGscale=itrend->second.GetMinHGscale();
    if(MaxHGscale<itrend->second.GetMaxHGscale()) MaxHGscale=itrend->second.GetMaxHGscale();
    
    if(MinHGLGcorr>itrend->second.GetMinHGLGcorr()) MinHGLGcorr=itrend->second.GetMinHGLGcorr();
    if(MaxHGLGcorr<itrend->second.GetMaxHGLGcorr()) MaxHGLGcorr=itrend->second.GetMaxHGLGcorr();
    if(MinLGHGcorr>itrend->second.GetMinLGHGcorr()) MinLGHGcorr=itrend->second.GetMinLGHGcorr();
    if(MaxLGHGcorr<itrend->second.GetMaxLGHGcorr()) MaxLGHGcorr=itrend->second.GetMaxLGHGcorr();
    
    itrend->second.SetXAxisTitle(xaxisTitle);
    itrend->second.Write(RootOutput);
  }
    
  //***********************************************************************************************************
  //********************************* 8 Panel overview plot  **************************************************
  //***********************************************************************************************************
  //*****************************************************************
  // Test beam geometry (beam coming from viewer)
  //===========================================================
  //||    8 (4)    ||    7 (5)   ||    6 (6)   ||    5 (7)   ||  row 0
  //===========================================================
  //||    1 (0)    ||    2 (1)   ||    3 (2)   ||    4 (3)   ||  row 1
  //===========================================================
  //    col 0     col 1       col 2     col  3
  // rebuild pad geom in similar way (numbering -1)
  //*****************************************************************
  TCanvas* canvas8Panel;
  TPad* pad8Panel[8];
  Double_t topRCornerX[8];
  Double_t topRCornerY[8];
  Int_t textSizePixel = 30;
  Double_t relSize8P[8];
  CreateCanvasAndPadsFor8PannelTBPlot(canvas8Panel, pad8Panel,  topRCornerX, topRCornerY, relSize8P, textSizePixel, 0.045);

  Int_t detailed = 0;
  for (Int_t l = 0; l < setup->GetNMaxLayer()+1; l++){    
    if (l%10 == 0 && l > 0 && debug > 0)
      std::cout << "============================== layer " <<  l << " / " << setup->GetNMaxLayer() << " layers" << std::endl;
    PlotTrendingPerLayer(     canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                              trend, 0, Xmin,Xmax, l, 0,
                              Form("%s/HGped_Layer%02d.%s" ,OutputNameDirPlots.Data(), l, plotSuffix.Data()),Form("%s/TrendHGPedestal",OutputNameDirPlots.Data()),detailed);        
    PlotTrendingPerLayer(     canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                              trend, 1, Xmin,Xmax, l, 0,
                              Form("%s/LGped_Layer%02d.%s" ,OutputNameDirPlots.Data(), l, plotSuffix.Data()),Form("%s/TrendLGPedestal",OutputNameDirPlots.Data()),detailed);        
    PlotTrendingPerLayer(     canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                              trend, 2, Xmin,Xmax, l, 0,
                              Form("%s/HGScale_Layer%02d.%s" ,OutputNameDirPlots.Data(), l, plotSuffix.Data()),Form("%s/TrendHGScale",OutputNameDirPlots.Data()),detailed);        
    PlotTrendingPerLayer(     canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                              trend, 3, Xmin,Xmax, l, 0,
                              Form("%s/LGScale_Layer%02d.%s" ,OutputNameDirPlots.Data(), l, plotSuffix.Data()),Form("%s/TrendLGScale",OutputNameDirPlots.Data()),detailed);        
    PlotTrendingPerLayer(     canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                              trend, 4, Xmin,Xmax, l, 0,
                              Form("%s/LGHGCorr_Layer%02d.%s" ,OutputNameDirPlots.Data(), l, plotSuffix.Data()),Form("%s/TrendLGHGCorr",OutputNameDirPlots.Data()),detailed);        
    PlotTrendingPerLayer(     canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                              trend, 5, Xmin,Xmax, l, 0,
                              Form("%s/HGLGCorr_Layer%02d.%s" ,OutputNameDirPlots.Data(), l, plotSuffix.Data()),Form("%s/TrendHGLGCorr",OutputNameDirPlots.Data()),detailed);        
  }  
  
  return status;
}


bool ComparisonCalib::CreateOutputRootFile(void){
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


