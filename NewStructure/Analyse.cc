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
#include "Analyses.h"

Setup* Setup::instancePtr=nullptr; // Remove for use on Mac OS -> Add to Setup.cc instead
//Calib* Calib::instancePtr=nullptr;

void PrintHelp(char* exe){
  std::cout<<"Usage:"<<std::endl;
  std::cout<<exe<<" [-option (arguments)]"<<std::endl;
  std::cout<<"Options:"<<std::endl;
  std::cout<<"-c xxx   Convert ASCII input file xxx into root format output"<<std::endl;
  std::cout<<"-C yyy   Apply calibrations stored in yyy root file to the input uncalibrated file"<<std::endl;
  std::cout<<"-p       Extract pedestal from input file and store it in output file"<<std::endl;
  std::cout<<"-y yyyy  setting year externally to narrow parameters"<<std::endl;
  std::cout<<"-P zzz   Correct pedestals stored in zzz root file and applied to input file"<<std::endl;
  std::cout<<"-i uuu   Input file in root format"<<std::endl;
  std::cout<<"-o vvv   Output file name (mandatory)"<<std::endl;
  std::cout<<"-O kkk   Output directory name for plots (mandatory)"<<std::endl;
  std::cout<<"-b       calculate bad channel map internally"<<std::endl;
  std::cout<<"-B lll   apply external bad channel map during transfer of calibs"<<std::endl;
  std::cout<<"-s       extract scaling constant from input data"<<std::endl;
  std::cout<<"-S       extract scaling constant from input data in 2nd iteration based on pretriggered data"<<std::endl;
  std::cout<<"-N       save noise triggered cells only"<<std::endl;
  std::cout<<"-M       save mip triggered cells only"<<std::endl;
  std::cout<<"-f       Force to write output if already exist"<<std::endl;
  std::cout<<"-m www   Name of mapping file  2024 PS TB [../configs/mappingFile_202409_CAEN.txt] "<<std::endl;
  std::cout<<"-r rrr   Name of run list file  2024 PS TB [../configs/DataTakingDB_202409_CAEN.csv] "<<std::endl;
  std::cout<<"-d [0-3] switch on debug info with debug level 0 to 3"<<std::endl;
  std::cout<<"-e       extended plotting = 1"<<std::endl;
  std::cout<<"-E       extended plotting = 2"<<std::endl;
  std::cout<<"-h       this help"<<std::endl<<std::endl;
  std::cout<<"Examples:"<<std::endl;
  std::cout<<exe<<" -c input.txt -o output.root (Convert ASCII to root)"<<std::endl;
  std::cout<<exe<<" -p (-f) -o OutputWithExtractedPedestal.root -i input.root (-f to overwrite existing output)"<<std::endl;
  std::cout<<exe<<" -s (-f) -o OutputWithMIPscaling.root -i input.root (-f to overwrite existing output)"<<std::endl;
  std::cout<<exe<<" -S (-f) -o OutputWithMIPscaling.root -i input.root (-f to overwrite existing output)"<<std::endl;
  std::cout<<exe<<" -s (-f) -o OutputWithMIPscaling.root -P PedestalInput.root -i RawInput.root (-f to overwrite existing output)"<<std::endl;
  std::cout<<exe<<" -C Calibration.root (-f) -o CalibratedOutput.root -i Input.root (-f to overwrite existing output)"<<std::endl;
}
  

int main(int argc, char* argv[]){
  if(argc<4) {
    PrintHelp(argv[0]);
    return 0;
  }
  Analyses AnAnalysis;
  int c;
  while((c=getopt(argc,argv,"c:pT:sk:P:SnbB:L:NtMC:fo:O:aA:eEm:d:i:y:r:h"))!=-1){
    switch(c){
    case 'a':
      std::cout<<"Analyses:: printing calib object to file"<<std::endl;
      AnAnalysis.IsCalibSaveToFile(true);
      break;
    case 'A':
      std::cout<<"Analyses:: stripping calib object to file: " << optarg<<std::endl;
      AnAnalysis.IsToSaveCalibOnly(true);
      AnAnalysis.SetRootCalibOutput(optarg);
      break;
    case 'b':
      std::cout<<"Analyses:: run Bad channel determination"<<std::endl;
      AnAnalysis.SetCalcBadChannel(2);
      break;
    case 'B':
      std::cout<<"Analyses:: read bad channel map from external file: "<<optarg<<std::endl;
      AnAnalysis.SetExternalBadChannelMap(Form("%s",optarg));
      AnAnalysis.SetCalcBadChannel(1);
      break;
    case 'c':
      std::cout<<"Analyses:: Convert ASCII input '"<<optarg<<"' to root format"<<std::endl;
      AnAnalysis.SetASCIIinput(Form("%s",optarg));
      AnAnalysis.IsToConvert(true);
      break;
    case 'C':
      std::cout<<"Analyses:: Apply calibration (pedestal correction and scaling factor) from: "<<optarg<<std::endl;
      AnAnalysis.SetRootCalibInput(Form("%s",optarg));
      AnAnalysis.IsToApplyCalibration(true);
      break;
    case 'd':
      std::cout<<"Analyses:: enable debug " << optarg <<std::endl;
      AnAnalysis.EnableDebug(atoi(optarg));
      break;
    case 'e':
      std::cout<<"Analyses:: enabling extended plotting"<<std::endl;
      AnAnalysis.SetExtPlotting(1);
      break;
    case 'E':
      std::cout<<"Analyses:: enabling more extended plotting"<<std::endl;
      AnAnalysis.SetExtPlotting(2);
      break;
    case 'f':
      std::cout<<"Analyses:: If output already exists it will be overwritten"<<std::endl;
      AnAnalysis.CanOverWrite(true);
      break;
    case 'i':
      std::cout<<"Analyses:: Root input file is: "<<optarg<<std::endl;
      AnAnalysis.SetRootInput(Form("%s",optarg));
      break;
    case 'k':
      std::cout<<"Analyses:: enable overwrite from external text file: "<< optarg <<std::endl;
      AnAnalysis.SetExternalCalibFile(optarg);
      AnAnalysis.SetOverWriteCalib(true);
      break;
    case 'L':
      std::cout<<"Analyses:: SetMaxEvents processed:"<<optarg<<std::endl;
      AnAnalysis.SetMaxEvents(atoi(optarg));
      break;
    case 'm':
      std::cout<<"Analyses:: Mapping file from: "<<optarg<<std::endl;
      AnAnalysis.SetMapInput(Form("%s",optarg));
      break;
    case 'M':
      std::cout<<"Analyses:: Save mip triggered cells only to create minimal sample"<<std::endl;
      AnAnalysis.IsToSaveMipsOnly(true);
      break;
    case 'n':
      std::cout<<"Analyses:: Extract noise after 1st mip fits and reevaluate pedestals"<<std::endl;
      AnAnalysis.IsToReextractNoise(true);
      break;
    case 'N':
      std::cout<<"Analyses:: Save noise only cells to create new pedestal"<<std::endl;
      AnAnalysis.IsToSaveNoiseOnly(true);
      break;
    case 'o':
      std::cout<<"Analyses:: Output to be saved in: "<<optarg<<std::endl;
      AnAnalysis.SetRootOutput(Form("%s",optarg));
      break;
    case 'O':
      std::cout<<"Analyses:: Outputdir plots to be saved in: "<<optarg<<std::endl;
      AnAnalysis.SetPlotOutputDir(Form("%s",optarg));
      break;
    case 'p':
      std::cout<<"Analyses:: Extract pedestal from input data"<<std::endl;
      AnAnalysis.IsToExtractPedestal(true);
      break;
    case 'P':
      std::cout<<"Analyses:: Apply pedestal correction from: "<<optarg<<std::endl;
      AnAnalysis.SetRootPedestalInput(Form("%s",optarg));
      AnAnalysis.IsToApplyPedestalCorrection(true);
      break;
    case 'r':
      std::cout<<"Analyses:: run list file from: "<<optarg<<std::endl;
      AnAnalysis.SetRunListInput(Form("%s",optarg));
      break;
    case 's':
      std::cout<<"Analyses:: Extract scaling constant from input data"<<std::endl;
      AnAnalysis.IsToExtractScaling(true);
      break;
    case 'S':
      std::cout<<"Analyses:: Extract scaling improved from 2nd iteration"<<std::endl;
      AnAnalysis.IsToExtractScalingImproved(true);
      break;
    case 't':
      std::cout<<"Analyses:: run without trigger eval, use from file" <<std::endl;
      AnAnalysis.UseLocTriggFromFile(true);
      break;
    case 'T':
      std::cout<<"Analyses:: run local trigger, with calib file:" << optarg<<std::endl;
      AnAnalysis.IsToEvalLocalTrigg(true);
      AnAnalysis.SetRootCalibInput(Form("%s",optarg));
      break;
    case 'y':
      std::cout<<"Analyses:: Setting year externally: "<<optarg<<std::endl;
      AnAnalysis.SetYear(atoi(optarg));
      break;
    case '?':
      std::cout<<"Analyses:: Option "<<optarg <<" not supported, will be ignored "<<std::endl;
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
