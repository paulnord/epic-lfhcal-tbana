#ifndef COMPARISONCALIB_H
#define COMPARISONCALIB_H

#include <iostream>
#include <fstream>
#include "TString.h"
#include "TFile.h"
#include "TChain.h"
#include "TObjString.h"

#include "Setup.h"
#include "RootSetupWrapper.h"
#include "Calib.h"
#include "Event.h"
#include "Tile.h"
#include "HGCROC.h"
#include "Caen.h"
    
class ComparisonCalib{

 public:
  ComparisonCalib(){
    TsetupIn = new TChain("Setup");
    TcalibIn = new TChain("Calib");
    rswptr=&rsw;
    calibptr=&calib;
  }
  ~ComparisonCalib(){
    if(RootOutput) RootOutput->Close();
  }

  //Getter methods
  inline TString GetRootCalibInputName()    const {return TcalibIn->GetFile()->GetName();};
  inline TString GetInputListName()         const {return InputListName;};
  inline TString GetRootOutputName()        const {return RootOutputName;};
  inline TString GetPlotOutputDir()         const {return OutputNameDirPlots;};
  
  inline TFile* GetRootOutput()        {return RootOutput;}

  inline bool CanOverWrite(void)                const {return Overwrite;};
  
  //setter methods
  //Overload method for boolean...or is it too dangerous?
  inline void CanOverWrite(bool b)               {Overwrite=b;};
  inline void EnableDebug(int i)                 {debug=i;};
  inline void ExpandedList(bool b)               {expandedList=b;};  
  
  inline void AddInputFile(TString name)         {RootInputNames.push_back(name);};
  inline void SetInputList(TString name)         {InputListName=name;};
  inline void SetRootOutput(TString name)        {RootOutputName =name;};
  inline void SetPlotOutputDir(TString name)     {OutputNameDirPlots =name;};
  inline void SetTrendingAxis(int i)            {Xaxis=i;};
  
  //General methods
  bool CreateOutputRootFile(void);
  bool CheckAndOpenIO(void);
  bool Process(void);

  //Variable members
  TString RootOutputName;                 // file name of root output with tree
  std::vector<TString> RootInputNames;    // file name of root output with tree
  //TString RootOutputNameHist;             // file name of root output with additional histograms & fits
  TString OutputNameDirPlots;             // directory name of output for plots
  TString plotSuffix        = "pdf";      // output file format for plots
  TString InputListName;                  // file name of input file list 
  TFile* RootOutput         =nullptr;     // root file output tree
  bool Overwrite              =false;     // Flag to overwrite outputs
  bool expandedList           =false;     // Expanded input list option
  int debug                   =0;         // debug level 
  int yearData                =-1;        // data taking year externally set
  int Xaxis                   =0;         // Trending dependence 0: run nr, 1: Voltage
  RootSetupWrapper rsw;                   // Wrapper singleton class for setup
  RootSetupWrapper* rswptr;               // Pointer to wrapper for singleton class for setup
  Setup* setup;                           // geometry setup
  Calib calib;                            // calibration object
  Calib* calibptr;                        // pointer to calib object
  
  TChain* TsetupIn=nullptr;
  TChain* TcalibIn=nullptr;

 protected:


 private:
   
};

#endif
