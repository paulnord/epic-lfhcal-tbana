#include "ComparisonCalib.h"
#include <vector>
#include "TROOT.h"
//#include <unistd.h> // Add for use on Mac OS -> Same goes for Analyse.cc
#include "TF1.h"
#include "TFitResult.h"
#include "TFitResultPtr.h"
#include "TH1D.h"
#include "TH2D.h"
#include "TProfile.h"
#include "TChain.h"
#include "TileSpectra.h"
#include "TileTrend.h"
#include "CommonHelperFunctions.h"
#include "PlottHelper.h"

bool ComparisonCalib::CheckAndOpenIO(void){
  int matchingbranch;
  
  if(!InputListName.IsNull()){
    //File exist?
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
    }
  }
  else {//we did not provide a txt file with a list of root file we want to process but directly the list of files to process
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
  bool status=true;
  ROOT::EnableImplicitMT();
  int entries=TcalibIn->GetEntries();
  std::map<int, TileTrend> trend;
  std::map<int, TileTrend>::iterator itrend;
  std::map<int, TileCalib>::const_iterator itcalib;
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
    if(Xvalue<Xmin) Xmin=Xvalue;
    if(Xvalue>Xmax) Xmax=Xvalue;
    for(itcalib=calib.begin(); itcalib!=calib.end(); ++itcalib){
      itrend=trend.find(itcalib->first);
      if(itrend!=trend.end()){
	itrend->second.Fill(Xvalue,itcalib->second);
      }
      else{
	TileTrend atrend=TileTrend(itcalib->first,0);
	atrend.Fill(Xvalue,itcalib->second);
	trend[itcalib->first]=atrend;
      }
    }
    //std::cout<<ientry<<" "<<calib.GetRunNumber()<<" "<<TcalibIn->GetFile()->GetName()<<std::endl;
    //std::cout<<ientry<<" "<<setup->GetTotalNbChannels()<<" "<<TsetupIn->GetFile()->GetName()<<std::endl;
  }
  
  double MaxLGped    =0.;
  double MaxHGped    =0.;
  double MaxLGscale  =0.;
  double MaxHGscale  =0.;
  double MaxHGLGcorr =0.;
  
  double MinLGped    =9999.;
  double MinHGped    =9999.;
  double MinLGscale  =9999.;
  double MinHGscale  =9999.;
  double MinHGLGcorr =9999.;

  for(itrend=trend.begin(); itrend!=trend.end(); ++itrend){
    if(MinLGped>itrend->second.GetMinLGped()) MinLGped=itrend->second.GetMinLGped();
    if(MaxLGped<itrend->second.GetMaxLGped()) MaxLGped=itrend->second.GetMaxLGped();
    if(MinHGped>itrend->second.GetMinHGped()) MinHGped=itrend->second.GetMinHGped();
    if(MaxHGped<itrend->second.GetMaxHGped()) MaxHGped=itrend->second.GetMaxHGped();
    
    if(MinLGscale>itrend->second.GetMinLGscale()) MinLGscale=itrend->second.GetMinLGscale();
    if(MaxLGscale<itrend->second.GetMaxLGscale()) MaxLGscale=itrend->second.GetMaxLGscale();
    if(MinHGscale>itrend->second.GetMinHGscale()) MinHGscale=itrend->second.GetMinHGscale();
    if(MaxHGscale<itrend->second.GetMaxHGscale()) MaxHGscale=itrend->second.GetMaxHGscale();
    
    if(MinHGLGcorr>itrend->second.GetMinHGHGcorr()) MinHGLGcorr=itrend->second.GetMinHGHGcorr();
    if(MaxHGLGcorr<itrend->second.GetMaxHGHGcorr()) MaxHGLGcorr=itrend->second.GetMaxHGHGcorr();

    itrend->second.Write(RootOutput);
    
  }

  if(debug>0){
    TCanvas* cLGped = new TCanvas("cLGped","cLGped");
    cLGped->Divide(4,2,0,0);
    cLGped->Print("TrendLGPedestal.pdf[");
    TCanvas* cHGped = new TCanvas("cHGped","cHGped");
    cHGped->Divide(4,2,0,0);
    cHGped->Print("TrendHGPedestal.pdf[");
    TCanvas* cLGscale = new TCanvas("cLGscale","cLGscale");
    cLGscale->Divide(4,2,0,0);
    cLGscale->Print("TrendLGScale.pdf[");
    TCanvas* cHGscale = new TCanvas("cHGscale","cHGscale");
    cHGscale->Divide(4,2,0,0);
    cHGscale->Print("TrendHGScale.pdf[");
    TCanvas* cHGLGcorr = new TCanvas("cHGLGcorr","cHGLGcorr");
    cHGLGcorr->Divide(4,2,0,0);
    cHGLGcorr->Print("TrendHGLGCorr.pdf[");
    TH2D* hframeLGped   ;
    TH2D* hframeHGped   ;
    TH2D* hframeLGscale ;
    TH2D* hframeHGscale ;
    TH2D* hframeHGLGcorr;
 
    if(Xaxis==2){
      hframeLGped   =new TH2D("frame1","",100,Xmin,Xmax,100,MinLGped*0.9>0?MinLGped*0.9:0,MaxLGped*1.1);
      hframeHGped   =new TH2D("frame2","",100,Xmin,Xmax,100,MinHGped*0.9>0?MinHGped*0.9:0,MaxHGped*1.1);
      hframeLGscale =new TH2D("frame3","",100,Xmin,Xmax,100,MinLGscale*0.9>0?MinLGscale*0.9:0,MaxLGscale*1.1);
      hframeHGscale =new TH2D("frame4","",100,Xmin,Xmax,100,MinHGscale*0.9>0?MinHGscale*0.9:0,MaxHGscale*1.1);
      hframeHGLGcorr=new TH2D("frame5","",100,Xmin,Xmax,100,MinHGLGcorr*0.9>0?MinHGLGcorr*0.9:0,MaxHGLGcorr*1.1);
      hframeLGped->GetXaxis()->SetTimeFormat("%d/%m/%y %H:%M %F1970-01-01 00:00:00s0");
      hframeLGped->GetXaxis()->SetTimeDisplay(kTRUE);
      hframeHGped->GetXaxis()->SetTimeFormat("%d/%m/%y %H:%M %F1970-01-01 00:00:00s0");
      hframeHGped->GetXaxis()->SetTimeDisplay(kTRUE);
      hframeLGscale->GetXaxis()->SetTimeFormat("%d/%m/%y %H:%M %F1970-01-01 00:00:00s0");
      hframeLGscale->GetXaxis()->SetTimeDisplay(kTRUE);
      hframeHGscale->GetXaxis()->SetTimeFormat("%d/%m/%y %H:%M %F1970-01-01 00:00:00s0");
      hframeHGscale->GetXaxis()->SetTimeDisplay(kTRUE);
      hframeHGLGcorr->GetXaxis()->SetTimeFormat("%d/%m/%y %H:%M %F1970-01-01 00:00:00s0");
      hframeHGLGcorr->GetXaxis()->SetTimeDisplay(kTRUE);
    }
    else{
      hframeLGped   =new TH2D("frame1","",100,0.9*Xmin,1.1*Xmax,100,MinLGped*0.9>0?MinLGped*0.9:0,MaxLGped*1.1);
      hframeHGped   =new TH2D("frame2","",100,0.9*Xmin,1.1*Xmax,100,MinHGped*0.9>0?MinHGped*0.9:0,MaxHGped*1.1);
      hframeLGscale =new TH2D("frame3","",100,0.9*Xmin,1.1*Xmax,100,MinLGscale*0.9>0?MinLGscale*0.9:0,MaxLGscale*1.1);
      hframeHGscale =new TH2D("frame4","",100,0.9*Xmin,1.1*Xmax,100,MinHGscale*0.9>0?MinHGscale*0.9:0,MaxHGscale*1.1);
      hframeHGLGcorr=new TH2D("frame5","",100,0.9*Xmin,1.1*Xmax,100,MinHGLGcorr*0.9>0?MinHGLGcorr*0.9:0,MaxHGLGcorr*1.1);
    }
    hframeLGped   ->SetStats(kFALSE);
    hframeHGped   ->SetStats(kFALSE);
    hframeLGscale ->SetStats(kFALSE);
    hframeHGscale ->SetStats(kFALSE);
    hframeHGLGcorr->SetStats(kFALSE);
    for(int lay=0; lay<64; lay++){
      for(int col=0; col<4; col++){
	for(int row=0; row<2; row++){
	  itrend=trend.find(setup->GetCellID(row,col,lay,0));
	  if(itrend!=trend.end()){
	    cLGped->cd(col+4*row+1);
	    hframeLGped->Draw();
	    itrend->second.DrawLGped("psame");
	    cHGped->cd(col+4*row+1);
	    hframeHGped->Draw();
	    itrend->second.DrawHGped("psame");
	  
	    cLGscale->cd(col+4*row+1);
	    hframeLGscale->Draw();
	    itrend->second.DrawLGscale("psame");
	    cHGscale->cd(col+4*row+1);
	    hframeHGscale->Draw();
	    itrend->second.DrawHGscale("psame");
	  
	    cHGLGcorr->cd(col+4*row+1);
	    hframeHGLGcorr->Draw();
	    itrend->second.DrawHGLGcorr("psame");
	  }
	}
      }
      cLGped->Print("TrendLGPedestal.pdf");
      cLGped->Clear("D");
      cHGped->Print("TrendHGPedestal.pdf");
      cHGped->Clear("D");
      cLGscale->Print("TrendLGScale.pdf");
      cLGscale->Clear("D");
      cHGscale->Print("TrendHGScale.pdf");
      cHGscale->Clear("D");
      cHGLGcorr->Print("TrendHGLGCorr.pdf");
      cHGLGcorr->Clear("D");
    }
    cLGped->Print("TrendLGPedestal.pdf]");
    cHGped->Print("TrendHGPedestal.pdf]");
    cLGscale->Print("TrendLGScale.pdf]");
    cHGscale->Print("TrendHGScale.pdf]");
    cHGLGcorr->Print("TrendHGLGCorr.pdf]");
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


