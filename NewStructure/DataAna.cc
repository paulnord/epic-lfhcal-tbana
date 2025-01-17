#include <iostream>
#include <fstream>
#include <vector>
#include <map>
#include <utility>
//#include <unistd.h> // Add for use on Mac OS -> Same goes for Analyses.cc
#include "TString.h"
#include "TFile.h"
#include "TTree.h"
#include "TCanvas.h"
#include "TF1.h"
#include "TH1D.h"
#include "TObjArray.h"
#include "TObjString.h"

#include "Setup.h"
#include "Calib.h"
#include "Event.h"
#include "Tile.h"
#include "HGCROC.h"
#include "Caen.h"
#include "DataAnalysis.h"

Setup* Setup::instancePtr=nullptr; // Remove for use on Mac OS -> Add to Setup.cc instead
//Calib* Calib::instancePtr=nullptr;

void PrintHelp(char* exe){
  std::cout<<"Usage:"<<std::endl;
  std::cout<<exe<<" [-option (arguments)]"<<std::endl;
  std::cout<<"Options:"<<std::endl;
  std::cout<<"I am in the right routine:"<<std::endl;
  
}
  

int main(int argc, char* argv[]){
  if(argc<4) {
    PrintHelp(argv[0]);
    return 0;
  }
  DataAnalysis AnAnalysis;
  int c;
  while((c=getopt(argc,argv,"afP:o:O:e:r:d:i:y:hQ"))!=-1){
    switch(c){
    case 'a':
      std::cout<<"printing calib object to file"<<std::endl;
      AnAnalysis.IsCalibSaveToFile(true);
      break;
    case 'f':
      std::cout<<"If output already exists it will be overwritten"<<std::endl;
      AnAnalysis.CanOverWrite(true);
      break;
    case 'O':
      std::cout<<"Output  Histsto be saved in: "<<optarg<<std::endl;
      AnAnalysis.SetRootOutputHists(Form("%s",optarg));
      break;
    case 'o':
      std::cout<<"Output to be saved in: "<<optarg<<std::endl;
      AnAnalysis.SetRootOutput(Form("%s",optarg));
      break;
    case 'P':
      std::cout<<"Outputdir plots to be saved in: "<<optarg<<std::endl;
      AnAnalysis.SetPlotOutputDir(Form("%s",optarg));
      break;
    case 'e':
      std::cout<<"enabling extended plotting: "<< optarg<<std::endl;
      AnAnalysis.SetExtPlotting(atoi(optarg));
      break;
    case 'Q':
      std::cout<<"running QA"<<std::endl;
      AnAnalysis.IsToRunQA(true);
      break;
    case 'r':
      std::cout<<"run list file from: "<<optarg<<std::endl;
      AnAnalysis.SetRunListInput(Form("%s",optarg));
      break;
    case 'i':
      std::cout<<"Root input file is: "<<optarg<<std::endl;
      AnAnalysis.SetRootInput(Form("%s",optarg));
      break;
    case 'y':
      std::cout<<"Setting year externally: "<<optarg<<std::endl;
      AnAnalysis.SetYear(atoi(optarg));
      break;
    case 'd':
      std::cout<<"enable debug " << optarg <<std::endl;
      AnAnalysis.EnableDebug(atoi(optarg));
      break;
    case '?':
      std::cout<<"Option "<<optarg <<" not supported, will be ignored "<<std::endl;
      break;
    case 'h':
      PrintHelp(argv[0]);
      return 0;
    }
  }
  if(!AnAnalysis.CheckAndOpenIO()){
    std::cout<<"Check input and configurations, inconsistency or error with I/O detected"<<std::endl;
    PrintHelp(argv[0]);
    return -1;
  }

  AnAnalysis.Process();
  std::cout<<"Exiting"<<std::endl;
  return 0;
}
