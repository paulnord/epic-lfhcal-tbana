#ifndef DataAnalysis_H
#define DataAnalysis_H

#include <iostream>
#include <fstream>
#include "TString.h"
#include "TFile.h"
#include "TTree.h"
#include "TObjString.h"

#include "Setup.h"
#include "RootSetupWrapper.h"
#include "Calib.h"
#include "Event.h"
#include "Tile.h"
#include "HGCROC.h"
#include "Caen.h"
    
class DataAnalysis{

 public:
  DataAnalysis(){
    eventptr=&event;
    rswptr=&rsw;
    calibptr=&calib;
  }
  ~DataAnalysis(){}

  //Getter methods
  inline TString GetRootInputName()         const {return RootInputName;};
  inline TString GetRootOutputName()        const {return RootOutputName;};
  inline TString GetPlotOutputDir()         const {return OutputNameDirPlots;};
  
  inline TFile* GetRootInput()         {return RootInput;}
  inline TFile* GetRootOutput()        {return RootOutput;}

  inline bool CanOverWrite(void)                const {return Overwrite;};
  inline bool IsCalibSaveToFile(void)           const {return SaveCalibToFile;};
  inline short GetExtPlotting(void)             const {return ExtPlot;};
  inline bool IsToRunQA(void)                   const {return RunQA;};
  
  //setter methods
  //Overload method for boolean...or is it too dangerous?
  inline void CanOverWrite(bool b)               {Overwrite=b;};
  inline void IsCalibSaveToFile(bool b)          {SaveCalibToFile=b;};
  inline void SetExtPlotting(short b)            {ExtPlot = b;};
  inline void EnableDebug(int i)                 {debug=i;};
  inline void IsToRunQA(bool b)                  {RunQA=b;};
  
  inline void SetYear(int year)                  {yearData=year;};
  inline void SetRunListInput(TString name)      {RunListInputName=name;};
  inline void SetRootInput(TString name)         {RootInputName=name;};
  inline void SetRootOutput(TString name)        {RootOutputName =name;};
  inline void SetRootOutputHists(TString name)   {RootOutputNameHist =name;};
  inline void SetPlotOutputDir(TString name)     {OutputNameDirPlots =name;};
  
  //General methods
  bool CreateOutputRootFile(void);
  bool CreateOutputRootFileHist(void);
  bool CheckAndOpenIO(void);
  bool Process(void);

  //Variable members
  TString RootOutputName;                 // file name of root output with tree
  TString RootOutputNameHist;             // file name of root output with additional histograms & fits
  TString OutputNameDirPlots;             // directory name of output for plots
  TString RootInputName;                  // file name of input root file 
  TString RunListInputName;               // file name run list 
  TFile* RootOutput         =nullptr;     // root file output tree
  TFile* RootOutputHist     =nullptr;     // root file output histos
  TFile* RootInput          =nullptr;     // root file input 
  bool RunQA                  = false;    // Flag to run QA routine
  bool SaveCalibToFile        =false;     // Flag to save calib objects to text file
  short ExtPlot               =0;         // Enable extended plotting
  bool Overwrite              =false;     // Flag to overwrite outputs
  int debug                   =0;         // debug level 
  int yearData                =-1;        // data taking year externally set
  RootSetupWrapper rsw;                   // Wrapper singleton class for setup
  RootSetupWrapper* rswptr;               // Pointer to wrapper for singleton class for setup
  Setup* setup;                           // geometry setup
  Calib calib;                            // calibration object
  Calib* calibptr;                        // pointer to calib object
  Event event;
  Event* eventptr;
  
  TTree* TsetupIn=nullptr;
  TTree* TsetupOut=nullptr;
  TTree* TdataIn=nullptr;
  TTree* TdataOut=nullptr;
  TTree* TcalibIn=nullptr;
  TTree* TcalibOut=nullptr;

 protected:


 private:
  bool QAData(void);
 };


#endif
