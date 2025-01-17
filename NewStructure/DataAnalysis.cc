#include "DataAnalysis.h"
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
bool DataAnalysis::CheckAndOpenIO(void){
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
  
  //Setup Output files
  if(!RootOutputName.IsNull()){    
    
    bool sCOF = CreateOutputRootFile();
    if (!sCOF) return false;
    
    TsetupOut = new TTree("Setup","Setup");
    setup=Setup::GetInstance();
    TsetupOut->Branch("setup",&rsw);
    TdataOut = new TTree("Data","Data");
    TdataOut->Branch("event",&event);
    TcalibOut = new TTree("Calib","Calib");
    TcalibOut->Branch("calib",&calib);
  } 
  
  //Setup Output files
  if(!RootOutputNameHist.IsNull()){    
    std::cout<<"Creating output file for hists: "<< RootOutputNameHist.Data() <<std::endl;
    bool sCOF = CreateOutputRootFileHist();
    if (!sCOF) return false;
  }
  
  if ( RootOutputName.IsNull() && RootOutputNameHist.IsNull()){
    std::cout<<"Output file name is missing, please add"<<std::endl;
    return false;
  }  
  
  return true;
}

// ****************************************************************************
// Primary process function to start all calibrations
// ****************************************************************************
bool DataAnalysis::Process(void){
  bool status;
  ROOT::EnableImplicitMT();
  
  // copy full calibration to different file and calculate energy
  if(RunQA){
    status=QAData();
  }  
  return status;
}



//***********************************************************************************************
//*********************** Calibration routine ***************************************************
//***********************************************************************************************
bool DataAnalysis::QAData(void){
  std::cout<<"QA data"<<std::endl;

  std::map<int,RunInfo> ri=readRunInfosFromFile(RunListInputName.Data(),debug,0);
  
  // create HG and LG histo's per channel
  TH2D* hspectraHGCorrvsCellID      = new TH2D( "hspectraHGCorr_vsCellID","ADC spectrum High Gain corrected vs CellID; cell ID; ADC_{HG} (arb. units)  ; counts ",
                                            setup->GetMaxCellID()+1, -0.5, setup->GetMaxCellID()+1-0.5, 4000,-200,3800);
  hspectraHGCorrvsCellID->SetDirectory(0);
  TH2D* hspectraLGCorrvsCellID      = new TH2D( "hspectraLGCorr_vsCellID","ADC spectrum Low Gain corrected vs CellID; cell ID; ADC_{LG} (arb. units)  ; counts  ",
                                            setup->GetMaxCellID()+1, -0.5, setup->GetMaxCellID()+1-0.5, 4000,-200,3800);
  hspectraLGCorrvsCellID->SetDirectory(0);
  TH2D* hspectraHGvsCellID      = new TH2D( "hspectraHG_vsCellID","ADC spectrum High Gain vs CellID; cell ID; ADC_{HG} (arb. units)   ; counts ",
                                            setup->GetMaxCellID()+1, -0.5, setup->GetMaxCellID()+1-0.5, 4000,0,4000);
  hspectraHGvsCellID->SetDirectory(0);
  TH2D* hspectraLGvsCellID      = new TH2D( "hspectraLG_vsCellID","ADC spectrum Low Gain vs CellID; cell ID; ADC_{LG} (arb. units)  ; counts",
                                            setup->GetMaxCellID()+1, -0.5, setup->GetMaxCellID()+1-0.5, 4000,0,4000);
  hspectraLGvsCellID->SetDirectory(0);
  TH2D* hspectraEnergyvsCellID  = new TH2D( "hspectraEnergy_vsCellID","Energy vs CellID; cell ID; E (mip eq./tile)    ; counts",
                                            setup->GetMaxCellID()+1, -0.5, setup->GetMaxCellID()+1-0.5, 6000,0,200);
  hspectraEnergyvsCellID->SetDirectory(0);
  TH2D* hspectraEnergyTotvsNCells  = new TH2D( "hspectraTotEnergy_vsNCells","Energy vs CellID; N_{Cells}; E_{tot} (mip eq./tile) ; counts",
                                            setup->GetMaxCellID()+1, -0.5, setup->GetMaxCellID()+1-0.5, 6000,0,1000);
  hspectraEnergyTotvsNCells->SetDirectory(0);
  TH2D* hspectraEnergyTotvsNCellsMuon  = new TH2D( "hspectraTotEnergy_vsNCellsMuon","Energy vs CellID; N_{Cells}; E_{tot} (mip eq./tile) ; counts",
                                            setup->GetMaxCellID()+1, -0.5, setup->GetMaxCellID()+1-0.5, 6000,0,1000);
  hspectraEnergyTotvsNCellsMuon->SetDirectory(0);


  TH2D* hspectraEnergyVsLayer  = new TH2D( "hspectraTotLayerEnergy_vsLayer","Energy in layer vs Layer; Layer; E_{layer} (mip eq./tile) ; counts",
                                            setup->GetNMaxLayer()+1, -0.5, setup->GetNMaxLayer()+1-0.5, 6000,0,1000);
  hspectraEnergyVsLayer->SetDirectory(0);
  TH2D* hspectraEnergyVsLayerMuon  = new TH2D( "hspectraTotLayerEnergy_vsLayerMuon","Energy in layer vs Layer Muon triggers; Layer; E_{layer} (mip eq./tile) ; counts",
                                            setup->GetNMaxLayer()+1, -0.5, setup->GetNMaxLayer()+1-0.5, 6000,0,1000);
  hspectraEnergyVsLayerMuon->SetDirectory(0);
  TH2D* hAverageXVsLayer  = new TH2D( "hAverageX_vsLayer","Av. X pos in layer vs Layer; Layer; X_{pos} (cm) ; counts",
                                            setup->GetNMaxLayer()+1, -0.5, setup->GetNMaxLayer()+1-0.5, 100,-10,10);
  hAverageXVsLayer->SetDirectory(0);
  TH2D* hAverageYVsLayer  = new TH2D( "hAverageX_vsLayer","Av. Y pos in layer vs Layer; Layer; Y_{pos} (cm) ; counts",
                                            setup->GetNMaxLayer()+1, -0.5, setup->GetNMaxLayer()+1-0.5, 50,-5,5);
  hAverageYVsLayer->SetDirectory(0);
  TH2D* hNCellsVsLayer  = new TH2D( "hnCells_vsLayer","NCells in layer vs Layer; Layer; N_{cells,layer} ; counts",
                                            setup->GetNMaxLayer()+1, -0.5, setup->GetNMaxLayer()+1-0.5, 9,-0.5,8.5);
  
  
  
  std::map<int,TileSpectra> hSpectra;
  std::map<int,TileSpectra> hSpectraTrigg;
  std::map<int, TileSpectra>::iterator ithSpectra;
  std::map<int, TileSpectra>::iterator ithSpectraTrigg;

  RootOutputHist->mkdir("IndividualCells");
  RootOutputHist->mkdir("IndividualCellsTrigg");
  
  Int_t runNr = -1;
  std::cout << "starting to run QA"<< std::endl;
  TcalibIn->GetEntry(0);
  int actCh1st = 0;
  double averageScale = calib.GetAverageScaleHigh(actCh1st);
  std::cout << "average HG mip: " << averageScale << "\t active ch: "<< actCh1st<< std::endl;
  
  int evts=TdataIn->GetEntries();
  int evtsMuon= 0;
  for(int i=0; i<evts; i++){
    TdataIn->GetEntry(i);
    if (i%5000 == 0 && debug > 0) std::cout << "Reading " <<  i << " / " << evts << " events" << std::endl;
    if (i == 0)runNr = event.GetRunNumber();
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
      hspectraHGvsCellID->Fill(aTile->GetCellID(), aTile->GetADCHigh());
      hspectraLGvsCellID->Fill(aTile->GetCellID(), aTile->GetADCLow());
      hspectraHGCorrvsCellID->Fill(aTile->GetCellID(), corrHG);
      hspectraLGCorrvsCellID->Fill(aTile->GetCellID(), corrLG);
      if(aTile->GetE()!=0){ 
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
      // read current tile
      ithSpectraTrigg=hSpectraTrigg.find(aTile->GetCellID());
      if (aTile->GetLocalTriggerBit() == 1){
        if(ithSpectraTrigg!=hSpectraTrigg.end()){
          ithSpectraTrigg->second.FillTrigger(aTile->GetLocalTriggerPrimitive());
          ithSpectraTrigg->second.FillSpectra(corrLG,corrHG);
        } else {
          RootOutputHist->cd("IndividualCellsTrigg");
          hSpectraTrigg[aTile->GetCellID()]=TileSpectra("mipTrigg",aTile->GetCellID(),calib.GetTileCalib(aTile->GetCellID()),debug);
          hSpectraTrigg[aTile->GetCellID()].FillTrigger(aTile->GetLocalTriggerPrimitive());
          hSpectraTrigg[aTile->GetCellID()].FillSpectra(corrLG,corrHG);
        }
        locMuon++;        
      }      
      
      ithSpectra=hSpectra.find(aTile->GetCellID());
      if (ithSpectra!=hSpectra.end()){
        ithSpectra->second.FillSpectra(corrLG,corrHG);
        ithSpectra->second.FillTrigger(aTile->GetLocalTriggerPrimitive());;
        ithSpectra->second.FillCorr(corrLG,corrHG);
      } else {
        RootOutputHist->cd("IndividualCells");
        hSpectra[aTile->GetCellID()]=TileSpectra("mip1st",aTile->GetCellID(),calib.GetTileCalib(aTile->GetCellID()),debug);
        hSpectra[aTile->GetCellID()].FillSpectra(corrLG,corrHG);;
        hSpectra[aTile->GetCellID()].FillTrigger(aTile->GetLocalTriggerPrimitive());;
        hSpectra[aTile->GetCellID()].FillCorr(corrLG,corrHG);
      }
    }
    if (nCells > 0) {

      int nLayerSingleCell = 0;
      for(ithLayer=layers.begin(); ithLayer!=layers.end(); ++ithLayer){
        if (ithLayer->second.nCells == 1) 
            nLayerSingleCell++;
      }
      double fracLayer1Cell = (double)nLayerSingleCell/(int)layers.size();
      // if ( fracLayer1Cell > 0.8){
      //   muontrigg = true;
      //   evtsMuon++;        
      // }
      double fracLocMuon = (double)locMuon/nCells;
      if (fracLocMuon > 0.6){ 
        muontrigg = true;
        evtsMuon++;
      }
      if (muontrigg && debug > 3){
          std::cout << "Muon triggered:\t" <<  fracLayer1Cell << "\t" << fracLocMuon << std::endl;
      }
      
      for(int l = 0; l < setup->GetNMaxLayer()+1;l++){
        ithLayer=layers.find(l);
        if (ithLayer!=layers.end()){          
          double avx     = ithLayer->second.avX/ithLayer->second.energy;
          double avy     = ithLayer->second.avY/ithLayer->second.energy;
          hspectraEnergyVsLayer->Fill(l,ithLayer->second.energy);
          if (muontrigg) hspectraEnergyVsLayerMuon->Fill(l,ithLayer->second.energy);
          hAverageXVsLayer->Fill(l,avx);
          hAverageYVsLayer->Fill(l,avy);
          hNCellsVsLayer->Fill(l,ithLayer->second.nCells);
          if (ithLayer->second.nCells == 1) 
            nLayerSingleCell++;
        } else {
          hspectraEnergyVsLayer->Fill(l,0.);
          if (muontrigg) hspectraEnergyVsLayerMuon->Fill(l,0.);
          hAverageXVsLayer->Fill(l,-20);
          hAverageYVsLayer->Fill(l,-20);
          hNCellsVsLayer->Fill(l,0);
        }
      }

      
      
      for(int j=0; j<event.GetNTiles(); j++){
        Caen* aTile=(Caen*)event.GetTile(j);
        // remove bad channels from output
        double energy = aTile->GetE();
        if(energy!=0){ 
          hspectraEnergyvsCellID->Fill(aTile->GetCellID(), energy);
          Etot=Etot+energy;
        } 
      }

      hspectraEnergyTotvsNCells->Fill(nCells,Etot);
      if(muontrigg) hspectraEnergyTotvsNCellsMuon->Fill(nCells,Etot);
    }
  }
  
  if (IsCalibSaveToFile()){
    TString fileCalibPrint = RootOutputName;
    fileCalibPrint         = fileCalibPrint.ReplaceAll(".root","_calib.txt");
    calib.PrintCalibToFile(fileCalibPrint);
  }
  
  RootInput->Close();      
  
  RootOutputHist->cd();

  hspectraHGvsCellID->Write();
  hspectraLGvsCellID->Write();
  hspectraHGCorrvsCellID->Write();
  hspectraLGCorrvsCellID->Write();
  hspectraEnergyvsCellID->Write();
  hspectraEnergyTotvsNCells->Write();
  hspectraEnergyTotvsNCellsMuon->Write();
  
  TH2D* hspectraEnergyTotvsNCells_WoMuon = (TH2D*)hspectraEnergyTotvsNCells->Clone("hspectraTotEnergy_vsNCells_woMuon");
  hspectraEnergyTotvsNCells_WoMuon->Sumw2();
  hspectraEnergyTotvsNCells_WoMuon->Add(hspectraEnergyTotvsNCellsMuon, -1);
  hspectraEnergyTotvsNCells_WoMuon->Write();
  
  hspectraEnergyTotvsNCells->Sumw2();
  TH1D* hspectraEnergyTot = (TH1D*)hspectraEnergyTotvsNCells->ProjectionY();
  hspectraEnergyTot->SetDirectory(0);
  TH1D* hspectraNCells = (TH1D*)hspectraEnergyTotvsNCells->ProjectionX();
  hspectraNCells->SetDirectory(0);
  hspectraEnergyTot->Write("hTotEnergy");
  hspectraNCells->Write("hNCells");

  hspectraEnergyTotvsNCellsMuon->Sumw2();
  TH1D* hspectraEnergyTotMuon = (TH1D*)hspectraEnergyTotvsNCellsMuon->ProjectionY();
  hspectraEnergyTotMuon->SetDirectory(0);
  TH1D* hspectraNCellsMuon = (TH1D*)hspectraEnergyTotvsNCellsMuon->ProjectionX();
  hspectraNCellsMuon->SetDirectory(0);
  hspectraEnergyTotMuon->Write("hTotEnergyMuon");
  hspectraNCellsMuon->Write("hNCellsMuon");
  
  TH1D* hspectraEnergyTotNonMuon = (TH1D*)hspectraEnergyTotvsNCells_WoMuon->ProjectionY();
  hspectraEnergyTotNonMuon->SetDirectory(0);
  TH1D* hspectraNCellsNonMuon = (TH1D*)hspectraEnergyTotvsNCells_WoMuon->ProjectionX();
  hspectraNCellsNonMuon->SetDirectory(0);
  hspectraEnergyTotNonMuon->Write("hTotEnergyNonMuon");
  hspectraNCellsNonMuon->Write("hNCellsNonMuon");
  
  hAverageXVsLayer->Write();
  hAverageYVsLayer->Write();
  hNCellsVsLayer->Write();
  hspectraEnergyVsLayer->Write();
  hspectraEnergyVsLayerMuon->Write();
  TH2D* hspectraEnergyVsLayer_WoMuon = (TH2D*)hspectraEnergyVsLayer->Clone("hspectraTotLayerEnergy_vsLayer_woMuon");
  hspectraEnergyVsLayer_WoMuon->Sumw2();
  hspectraEnergyVsLayer_WoMuon->Add(hspectraEnergyVsLayerMuon, -1);
  hspectraEnergyVsLayer_WoMuon->Write();

  
  //**********************************************************************
  //********************* Plotting ***************************************
  //**********************************************************************
  // Get run info object
  std::map<int,RunInfo>::iterator it=ri.find(runNr);
  
  TString outputDirPlots = GetPlotOutputDir();
  gSystem->Exec("mkdir -p "+outputDirPlots);
  
  //**********************************************************************
  // Create canvases for channel overview plotting
  //**********************************************************************
  Double_t textSizeRel = 0.035;
  StyleSettingsBasics("pdf");
  SetPlotStyle();
  
  TCanvas* canvas2DCorr = new TCanvas("canvasCorrPlots","",0,0,1450,1300);  // gives the page size
  DefaultCancasSettings( canvas2DCorr, 0.08, 0.13, 0.045, 0.07);
  canvas2DCorr->SetLogz(1);
  PlotSimple2D( canvas2DCorr, hspectraHGvsCellID, -10000, -10000, textSizeRel, Form("%s/HG.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true);
  PlotSimple2D( canvas2DCorr, hspectraLGvsCellID, -10000, -10000, textSizeRel, Form("%s/LG.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true);
  PlotSimple2D( canvas2DCorr, hspectraHGCorrvsCellID, -10000, -10000, textSizeRel, Form("%s/HGCorr.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true);
  PlotSimple2D( canvas2DCorr, hspectraLGCorrvsCellID, -10000, -10000, textSizeRel, Form("%s/LGCorr.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true);
  PlotSimple2D( canvas2DCorr, hspectraEnergyvsCellID, -10000, -10000, textSizeRel, Form("%s/EnergyVsCellID.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true);
  PlotSimple2D( canvas2DCorr, hspectraEnergyTotvsNCells, -10000, -10000, textSizeRel, Form("%s/EnergyTotalVsNCells.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true, Form("evts = %d",evts));
  PlotSimple2D( canvas2DCorr, hspectraEnergyTotvsNCellsMuon, -10000, -10000, textSizeRel, Form("%s/EnergyTotalVsNCells_MuonTrigg.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true, Form("Muon evts = %d",evtsMuon));
  PlotSimple2D( canvas2DCorr, hspectraEnergyTotvsNCells_WoMuon, -10000, -10000, textSizeRel, Form("%s/EnergyTotalVsNCells_WoMuonTrigg.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true, Form("Non Muon evts = %d",evts-evtsMuon));


  PlotSimple2D( canvas2DCorr, hspectraEnergyVsLayer, -10000, -10000, textSizeRel, Form("%s/EnergyVsLayer.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true);
  PlotSimple2D( canvas2DCorr, hspectraEnergyVsLayerMuon, -10000, -10000, textSizeRel, Form("%s/EnergyVsLayer_MuonTrigg.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true, "Muon triggers");
  PlotSimple2D( canvas2DCorr, hspectraEnergyVsLayer_WoMuon, -10000, -10000, textSizeRel, Form("%s/EnergyVsLayer_WOMuonTrigg.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true, "Non Muon triggers");
  PlotSimple2D( canvas2DCorr, hAverageXVsLayer, -10000, -10000, textSizeRel, Form("%s/XPosVsLayer.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true);
  PlotSimple2D( canvas2DCorr, hAverageYVsLayer, -10000, -10000, textSizeRel, Form("%s/YPosVsLayer.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true);
  PlotSimple2D( canvas2DCorr, hNCellsVsLayer, -10000, -10000, textSizeRel, Form("%s/NcellsLayerVsLayer.pdf", outputDirPlots.Data()), it->second, 1, kFALSE, "colz", true);
  
  
  TCanvas* canvas1DSimple = new TCanvas("canvas1DSimple","",0,0,1450,1300);  // gives the page size
  DefaultCancasSettings( canvas1DSimple, 0.08, 0.03, 0.03, 0.07);
  hspectraEnergyTot->Scale(1./evts);
  hspectraEnergyTot->GetYaxis()->SetTitle("counts/event");
  PlotSimple1D(canvas1DSimple, hspectraEnergyTot, -10000, -10000, textSizeRel, Form("%s/EnergyTot.pdf", outputDirPlots.Data()), it->second, 1, Form("#LT E_{Tot} #GT = %.1f (mip/tile eq.)",hspectraEnergyTot->GetMean() ));

  hspectraEnergyTotMuon->Scale(1./evts);
  hspectraEnergyTotNonMuon->Scale(1./evts);
  PlotContamination1D(canvas1DSimple, hspectraEnergyTot,hspectraEnergyTotMuon, hspectraEnergyTotNonMuon, -10000, -10000, textSizeRel, Form("%s/EnergyTotSplit.pdf", outputDirPlots.Data()), it->second, 1, Form("#LT E_{Tot,non muon} #GT = %.1f (mip/tile eq.)",hspectraEnergyTotNonMuon->GetMean() ));

  hspectraNCells->Scale(1./evts);
  hspectraNCells->GetYaxis()->SetTitle("counts/event");
  PlotSimple1D(canvas1DSimple, hspectraNCells, -10000, -10000, textSizeRel, Form("%s/NCells.pdf", outputDirPlots.Data()), it->second, 1, Form("#LT N_{Cells} #GT = %.1f",hspectraNCells->GetMean() ));
  hspectraNCellsMuon->Scale(1./evts);
  hspectraNCellsNonMuon->Scale(1./evts);  
  PlotContamination1D( canvas1DSimple, hspectraNCells, hspectraNCellsMuon, hspectraNCellsNonMuon, -10000, -10000, textSizeRel, Form("%s/NCellsSplit.pdf", outputDirPlots.Data()), it->second, 1, Form("#LT N_{Cells,non muon} #GT = %.1f",hspectraNCellsNonMuon->GetMean() ));
  
  
  if (ExtPlot > 0){
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
    CreateCanvasAndPadsFor8PannelTBPlot(canvas8Panel, pad8Panel,  topRCornerX, topRCornerY, relSize8P, textSizePixel);
  
    TCanvas* canvas8PanelProf;
    TPad* pad8PanelProf[8];
    Double_t topRCornerXProf[8];
    Double_t topRCornerYProf[8];
    Double_t relSize8PProf[8];
    CreateCanvasAndPadsFor8PannelTBPlot(canvas8PanelProf, pad8PanelProf,  topRCornerXProf, topRCornerYProf, relSize8PProf, textSizePixel, 0.045, "Prof", false);

    
    calib.PrintGlobalInfo();  
    Double_t maxHG = ReturnMipPlotRangeDepVov(calib.GetVov(),true);
    Double_t maxLG = 3800;
    std::cout << "plotting single layers" << std::endl;
    for (Int_t l = 0; l < setup->GetNMaxLayer()+1; l++){    
      if (l%10 == 0 && l > 0 && debug > 0){
        std::cout << "============================== layer " <<  l << " / " << setup->GetNMaxLayer() << " layers" << std::endl;
      }
      PlotMipWithFitsFullLayer (canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                              hSpectra, hSpectraTrigg, setup, true, -100, 3800, 1.2, l, 0,
                              Form("%s/LocTriggerMip_HG_Layer%02d.pdf" ,outputDirPlots.Data(), l), it->second);
      PlotMipWithFitsFullLayer (canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                              hSpectra, hSpectraTrigg, setup, true, -100, maxHG, 1.2, l, 0,
                              Form("%s/LocTriggerMip_Zoomed_HG_Layer%02d.pdf" ,outputDirPlots.Data(), l), it->second);
      PlotTriggerPrimWithFitsFullLayer (canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                                        hSpectra, setup, averageScale, 0.8, 2.,
                                        0, 6000, 1.2, l, 0, Form("%s/All_TriggPrimitive_Layer%02d.pdf" ,outputDirPlots.Data(), l), it->second);
      if (ExtPlot > 1){
        PlotCorrWithFitsFullLayer(canvas8PanelProf,pad8PanelProf, topRCornerXProf, topRCornerYProf, relSize8PProf, textSizePixel, 
                                      hSpectra, setup, false, -20, 800, 1.2, l, 0,
                                      Form("%s/LGHG_Corr_Layer%02d.pdf" ,outputDirPlots.Data(), l), it->second);
        PlotMipWithFitsFullLayer (canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                                  hSpectra, hSpectraTrigg, setup, false, -20, maxLG, 1.2, l, 0,
                                  Form("%s/LocTriggerMip_LG_Layer%02d.pdf" ,outputDirPlots.Data(), l), it->second);
        PlotTriggerPrimWithFitsFullLayer (canvas8Panel,pad8Panel, topRCornerX, topRCornerY, relSize8P, textSizePixel, 
                                          hSpectraTrigg, setup, averageScale, 0.8, 2.,
                                          0, maxHG*2, 1.2, l, 0, Form("%s/LocalMuon_TriggPrimitive_Layer%02d.pdf" ,outputDirPlots.Data(), l), it->second);
      }
    }
    std::cout << "done plotting" << std::endl;
  }
  RootOutputHist->Close();
  return true;
}

//***********************************************************************************************
//*********************** Create output files ***************************************************
//***********************************************************************************************
bool DataAnalysis::CreateOutputRootFile(void){
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

//***********************************************************************************************
//*********************** Create output files ***************************************************
//***********************************************************************************************
bool DataAnalysis::CreateOutputRootFileHist(void){
  if(Overwrite){
    RootOutputHist=new TFile(RootOutputNameHist.Data(),"RECREATE");
  } else{
    RootOutputHist = new TFile(RootOutputNameHist.Data(),"CREATE");
  }
  if(RootOutputHist->IsZombie()){
    std::cout<<"Error opening '"<<RootOutputHist<<"'no reachable path? Exist without force mode to overwrite?..."<<std::endl;
    return false;
  }
  return true;
}
