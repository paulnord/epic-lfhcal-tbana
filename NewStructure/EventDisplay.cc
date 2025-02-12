#include "EventDisplay.h"
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
#include "CommonHelperFunctions.h"
#include "TileSpectra.h"
#include "PlottHelper.h"
#include "TRandom3.h"
#include "TMath.h"
#include "Math/Minimizer.h"
#include "Math/MinimizerOptions.h"

// ****************************************************************************
// Checking and opening input and output files
// ****************************************************************************
bool EventDisplay::CheckAndOpenIO(void){
  int matchingbranch;

  //Need to check first input to get the setup...I do not think it is necessary
  std::cout<<"Input name set to: '"<<RootInputName.Data() <<std::endl;  
  if(!RootInputName.IsNull()){
    //File exist?
    RootInput=new TFile(RootInputName.Data(),"READ");
    if(RootInput->IsZombie()){
      std::cout<<"Error opening '"<<RootInputName<<"', does the file exist?"<<std::endl;
      return false;
    }

    //Retrieve info, start with setup
    TsetupIn = (TTree*) RootInput->Get("Setup");
    if(!TsetupIn){
      std::cout<<"Could not retrieve the Setup tree, leaving"<<std::endl;
      return false;
    }
    setup=Setup::GetInstance();
    std::cout<<"Setup add "<<setup<<std::endl;
    //matchingbranch=TsetupIn->SetBranchAddress("setup",&setup);
    matchingbranch=TsetupIn->SetBranchAddress("setup",&rswptr);
    if(matchingbranch<0){
      std::cout<<"Error retrieving Setup info from the tree"<<std::endl;
      return false;
    }
    std::cout<<"Entries "<<TsetupIn->GetEntries()<<std::endl;
    TsetupIn->GetEntry(0);
    setup->Initialize(*rswptr);
    std::cout<<"Reading "<<RootInput->GetName()<<std::endl;
    std::cout<<"Setup Info "<<setup->IsInit()<<"  and  "<<setup->GetCellID(0,0)<<std::endl;
    //std::cout<<"Setup add now "<<setup<<std::endl;

    //Retrieve info, existing data?
    TdataIn = (TTree*) RootInput->Get("Data");
    if(!TdataIn){
      std::cout<<"Could not retrieve the Data tree, leaving"<<std::endl;
      return false;
    }
    matchingbranch=TdataIn->SetBranchAddress("event",&eventptr);
    if(matchingbranch<0){
      std::cout<<"Error retrieving Event info from the tree"<<std::endl;
      return false;
    }
    
    TcalibIn = (TTree*) RootInput->Get("Calib");
    if(!TcalibIn){
      std::cout<<"Could not retrieve Calib tree, leaving"<<std::endl;
      //return false;
    }
    else {
      matchingbranch=TcalibIn->SetBranchAddress("calib",&calibptr);
      if(matchingbranch<0){
        std::cout<<"Error retrieving calibration info from the tree"<<std::endl;
        TcalibIn=nullptr;
      }
    }
  } else {
    std::cout<<"An input file is required, aborting"<<std::endl;
    return false;
  }  

  return true;
}

// ****************************************************************************
// Primary process function to start all calibrations
// ****************************************************************************
bool EventDisplay::Process(void){
  bool status;
  ROOT::EnableImplicitMT();
  
  // copy full calibration to different file and calculate energy
  status=Plot();

  return status;
}


//***********************************************************************************************
//*********************** Calibration routine ***************************************************
//***********************************************************************************************
bool EventDisplay::Plot(){
  std::cout<<"Plotting events "<<plotEvt<<" to " << plotEvt+nEvts-1<<std::endl;
  if(plotMuonEvts) std::cout<<"Plotting muon-triggered events"<<std::endl;

  std::map<int,RunInfo> ri=readRunInfosFromFile(RunListInputName.Data(),debug,0);
  TdataIn->GetEntry(0);
  Int_t runNr = event.GetRunNumber();
  // Get run info object
  std::map<int,RunInfo>::iterator it=ri.find(runNr);

  int species = -1;
  species = GetSpeciesIntFromRunInfo(it->second);
  if (species == -1){
      std::cout << "WARNING: species unknown: " << it->second.species.Data() << "  aborting"<< std::endl;
      return false;
  }
  
  // create 3D histo
  int towersx       = 4;
  int towersy       = 2; 
  int towersz       = 64;
  TH3F*   hXYZMapEvt    = new TH3F("hXYZMapEvt","",towersz, 0, 140, towersx, -10, 10, towersy, -5, 5);

// creating plotting directory
  TString outputDirPlots = GetPlotOutputDir();
  gSystem->Exec("mkdir -p "+outputDirPlots);
  
  TCanvas* canvas3D = new TCanvas("canvas3D","",0,0,1400,750);  // gives the page size
  DefaultCancasSettings( canvas3D, 0.12, 0.08, 0.05, 0.1);

  int evts=TdataIn->GetEntries();
  int evtsMuon= 0;
  for(int i=plotEvt; i<plotEvt+nEvts; i++){
    if(i > evts ) {
      std::cout<<"Requested event outside of the range. Aborting..."<<std::endl;
      return false;
    }
    TdataIn->GetEntry(i);
    // if (i%5000 == 0 && debug > 0) std::cout << "Reading " <<  i << " / " << evts << " events" << std::endl;
    double Etot = 0;
    int nCells  = 0;
    bool muontrigg = false;
    int locMuon = 0;
    std::map<int,Layer> layers;
    std::map<int, Layer>::iterator ithLayer;
    
    for(int j=0; j<event.GetNTiles(); j++){
      Caen* aTile=(Caen*)event.GetTile(j);
      double corrHG = aTile->GetADCHigh()-calib.GetPedestalMeanH(aTile->GetCellID());
      double corrLG = aTile->GetADCLow()-calib.GetPedestalMeanL(aTile->GetCellID());
      if(aTile->GetE()>0.3 ){ 
        nCells++;
        int currLayer = setup->GetLayer(aTile->GetCellID());
        ithLayer=layers.find(currLayer);
        if(ithLayer!=layers.end()){
          ithLayer->second.nCells+=1;
          ithLayer->second.energy+=aTile->GetE();
          ithLayer->second.avX+=setup->GetX(aTile->GetCellID())*aTile->GetE();
          ithLayer->second.avY+=setup->GetY(aTile->GetCellID())*aTile->GetE();
        } else {
          layers[currLayer]=Layer();
          layers[currLayer].nCells+=1;
          layers[currLayer].energy+=aTile->GetE();
          layers[currLayer].avX+=setup->GetX(aTile->GetCellID())*aTile->GetE();
          layers[currLayer].avY+=setup->GetY(aTile->GetCellID())*aTile->GetE();
        }
      }

      if (aTile->GetLocalTriggerBit() == 1){
        locMuon++;        
      }      
    }
    
    if (nCells > 0) {
      int nLayerSingleCell = 0;
      for(ithLayer=layers.begin(); ithLayer!=layers.end(); ++ithLayer){
        if (ithLayer->second.nCells == 1) 
            nLayerSingleCell++;
      }
      double fracLayer1Cell = (double)nLayerSingleCell/(int)layers.size();
      double fracLocMuon = (double)locMuon/nCells;
      if (fracLocMuon > 0.6){ 
        muontrigg = true;
        evtsMuon++;
      }
      if (muontrigg && debug > 3){
          std::cout << "Muon triggered:\t" <<  fracLayer1Cell << "\t" << fracLocMuon << std::endl;
      }
      for(int j=0; j<event.GetNTiles(); j++){
        Caen* aTile=(Caen*)event.GetTile(j);
        // remove bad channels from output
        double energy = aTile->GetE();
        if(energy>0.3){ 
          hXYZMapEvt->Fill(aTile->GetZ(),aTile->GetX(),aTile->GetY(),energy);
          if(debug > 2) std::cout << "Event, z, x, y, E: " << i << "\t" << aTile->GetZ()<< "\t" <<aTile->GetX()<< "\t" <<aTile->GetY()<< "\t" <<energy<<std::endl;
        } 
      }

      //**********************************************************************
      //********************* Plotting ***************************************
      //**********************************************************************  

      //**********************************************************************
      // Create canvases for channel overview plotting
      //**********************************************************************
      Double_t textSizeRel = 0.035;
      StyleSettingsBasics("pdf");
      SetPlotStyle();
      if( (muontrigg&&plotMuonEvts) || !plotMuonEvts){
        canvas3D->cd();

        SetStyleHistoTH3ForGraphs(hXYZMapEvt, "z", "x","y", 0.85*textSizeRel,textSizeRel, 0.85*textSizeRel,textSizeRel, 0.85*textSizeRel,textSizeRel, 1.1, 1.1, 1.15, 505, 510,510);
        hXYZMapEvt->Draw("box2z");
        DrawLatex(0.05, 0.94, GetStringFromRunInfo(it->second, 1), false, 0.85*textSizeRel, 42);
        if(muontrigg) DrawLatex(0.05, 0.90, Form("Event %d, muon triggered",i), false, 0.85*textSizeRel, 42);
        else DrawLatex(0.05, 0.90, Form("Event %d",i), false, 0.85*textSizeRel, 42);
        canvas3D->SaveAs( Form("%s/EventDisplay_evt%i.%s", outputDirPlots.Data(), i, plotSuffix.Data()));
        // canvas3D;
      }
    }

    hXYZMapEvt->Reset();
  }

    delete hXYZMapEvt;
    delete canvas3D;
    return true;
}
