#include "Calib.h"
#include <iostream>
#include <fstream>

ClassImp(Calib);

//*****************************************************************************************
// CALIBRATION Getters by cell ID
//*****************************************************************************************
double Calib::GetPedestalMeanH(int cellID) const{
  //std::map<int, double>::const_iterator it= PedestalMeanH.find(cellID);
  //if(it!=PedestalMeanH.end()) return it->second;
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.PedestalMeanH;
  else return 9999;
}

double Calib::GetPedestalMeanL(int cellID) const{
  //std::map<int, double>::const_iterator it= PedestalMeanL.find(cellID);
  //if(it!=PedestalMeanL.end()) return it->second;
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.PedestalMeanL;
  else return 9999;
}

double Calib::GetPedestalSigH(int cellID) const{
  //std::map<int, double>::const_iterator it= PedestalSigH.find(cellID);
  //if(it!=PedestalSigH.end()) return it->second;
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.PedestalSigH;
  else return 9999;
}
double Calib::GetPedestalSigL(int cellID) const{
  //std::map<int, double>::const_iterator it= PedestalSigL.find(cellID);
  //if(it!=PedestalSigL.end()) return it->second;
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.PedestalSigL;
  else return 9999;
}

double Calib::GetScaleHigh(int cellID)const {
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.ScaleH;
  else return -1.;
}

double Calib::GetScaleWidthHigh(int cellID)const {
  //std::map<int, double>::const_iterator it=ScaleH.find(cellID);
  //if(it!=ScaleH.end()) return it->second;
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.ScaleWidthH;
  else return -1.;
}

double Calib::GetScaleLow(int cellID) const {
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.ScaleL;
  else return -1.;
}

double Calib::GetScaleWidthLow(int cellID) const {
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.ScaleWidthL;
  else return -1.;
}

double Calib::GetScaleLGHGCorr(int cellID) const {
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.LGHGCorr;
  else return -1.;
}

double Calib::GetScaleHGLGCorr(int cellID) const {
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.HGLGCorr;
  else return -1.;
}

short Calib::GetBadChannel(int cellID) const {
  std::map<int, TileCalib>::const_iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()) return it->second.BadChannel;
  else return -1.;
}

//*****************************************************************************************
// CALIBRATION Getters by cell row, col, layer and module
//*****************************************************************************************
double Calib::GetPedestalMeanH(int row, int col, int lay, int mod=0) const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetPedestalMeanH(key);
}

double Calib::GetPedestalMeanL(int row, int col, int lay, int mod=0) const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetPedestalMeanL(key);
}

double Calib::GetPedestalSigH(int row, int col, int lay, int mod=0) const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetPedestalSigH(key);
}

double Calib::GetPedestalSigL(int row, int col, int lay, int mod=0) const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetPedestalSigL(key);
}

double Calib::GetScaleHigh(int row, int col, int lay, int mod=0)const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col,lay,mod);
  return GetScaleHigh(key);
}

double Calib::GetScaleWidthHigh(int row, int col, int lay, int mod=0)const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col,lay,mod);
  return GetScaleWidthHigh(key);
}

double Calib::GetScaleLow(int row, int col, int lay, int mod=0)const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetScaleLow(key);
}

double Calib::GetScaleWidthLow(int row, int col, int lay, int mod=0)const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetScaleWidthLow(key);
}

double Calib::GetScaleLGHGCorr(int row, int col, int lay, int mod=0)const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetScaleLGHGCorr(key);
}

double Calib::GetScaleHGLGCorr(int row, int col, int lay, int mod=0)const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetScaleHGLGCorr(key);
}

short Calib::GetBadChannel(int row, int col, int lay, int mod=0)const{
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetBadChannel(key);
}

//*****************************************************************************************
// CALIBRATION Average calculators
//*****************************************************************************************
double Calib::GetAveragePedestalMeanHigh()const{
  double avSc = 0;
  std::map<int, TileCalib>::const_iterator it;
  for(it=CaloCalib.begin(); it!=CaloCalib.end(); ++it){
    avSc += it->second.PedestalMeanH;
  }
  return avSc/CaloCalib.size();
}

double Calib::GetAverageScaleHigh(int &active )const{
  double avSc   = 0;
  int notCalib  = 0;
  std::map<int, TileCalib>::const_iterator it;
  for(it=CaloCalib.begin(); it!=CaloCalib.end(); ++it){
    if (it->second.ScaleH == -1000 || (BCcalc && it->second.BadChannel < 2) ){
      notCalib++;
    } else {
      avSc += it->second.ScaleH;
    }
  }
  active=(CaloCalib.size()-notCalib);
  return avSc/(CaloCalib.size()-notCalib);
}

double Calib::GetAverageScaleWidthHigh()const{
  double avSc = 0;
  int notCalib  = 0;
  std::map<int, TileCalib>::const_iterator it;
  for(it=CaloCalib.begin(); it!=CaloCalib.end(); ++it){
    if (it->second.ScaleWidthH == -1000 || (BCcalc && it->second.BadChannel < 2) ){
      notCalib++;
    } else {
      avSc += it->second.ScaleWidthH;
    }
  }
  return avSc/(CaloCalib.size()-notCalib);
}

double Calib::GetAverageScaleLow()const{
  double avSc = 0;
  int notCalib  = 0;
  std::map<int, TileCalib>::const_iterator it;
  for(it=CaloCalib.begin(); it!=CaloCalib.end(); ++it){
    if (it->second.ScaleL == -1000 || (BCcalc && it->second.BadChannel < 2) ){
      notCalib++;
    } else {
      avSc += it->second.ScaleL;
    }
  }
  return avSc/(CaloCalib.size()-notCalib);
}
double Calib::GetAverageScaleWidthLow()const{
  double avSc = 0;
  int notCalib  = 0;
  std::map<int, TileCalib>::const_iterator it;
  for(it=CaloCalib.begin(); it!=CaloCalib.end(); ++it){
    if (it->second.ScaleWidthL == -1000 || (BCcalc && it->second.BadChannel < 2) ){
      notCalib++;
    } else {
      avSc += it->second.ScaleWidthL;
    }
  }
  return avSc/(CaloCalib.size()-notCalib);
}

double Calib::GetAverageLGHGCorr()const{
  double avSc = 0;
  int notCalib  = 0;
  std::map<int, TileCalib>::const_iterator it;
  for(it=CaloCalib.begin(); it!=CaloCalib.end(); ++it){
    if (it->second.LGHGCorr == -64. || (BCcalc && it->second.BadChannel < 2) ){
      notCalib++;
    } else {
      avSc += it->second.LGHGCorr;
    }
  }
  return avSc/(CaloCalib.size()-notCalib);
}

double Calib::GetAverageHGLGCorr()const{
  double avSc = 0;
  int notCalib  = 0;
  std::map<int, TileCalib>::const_iterator it;
  for(it=CaloCalib.begin(); it!=CaloCalib.end(); ++it){
    if (it->second.HGLGCorr == -64. || (BCcalc && it->second.BadChannel < 2) ){
      notCalib++;
    } else {
      avSc += it->second.HGLGCorr;
    }
  }
  return avSc/(CaloCalib.size()-notCalib);
}


int Calib::GetNumberOfChannelsWithBCflag( short bcflag )const{
  int nCh = 0;
  std::map<int, TileCalib>::const_iterator it;
  for(it=CaloCalib.begin(); it!=CaloCalib.end(); ++it){
    if (bcflag == it->second.BadChannel)
      nCh++;
  }
  return nCh;
}


//*****************************************************************************************
// Getters for full calib objects
//*****************************************************************************************
TileCalib* Calib::GetTileCalib(int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    return &(it->second);
  }
  else {
    TileCalib acal;
    CaloCalib[cellID]=acal;
    return &(CaloCalib[cellID]);
  }
}

TileCalib* Calib::GetTileCalib(int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row, col, lay, mod);
  return GetTileCalib(key);
}

//*****************************************************************************************
// CALIBRATION Setters by cell ID
//*****************************************************************************************
void Calib::SetPedestalMeanH(double ped, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.PedestalMeanH=ped;
    CaloCalib[cellID]=acal;
  }
  else it->second.PedestalMeanH=ped;
}

void Calib::SetPedestalMeanL(double ped, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.PedestalMeanL=ped;
    CaloCalib[cellID]=acal;
  }
  else it->second.PedestalMeanL=ped;
}

void Calib::SetPedestalSigH(double ped, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.PedestalSigH=ped;
    CaloCalib[cellID]=acal;
  }
  else it->second.PedestalSigH=ped;
}

void Calib::SetPedestalSigL(double ped, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.PedestalSigL=ped;
    CaloCalib[cellID]=acal;
  }
  else it->second.PedestalSigL=ped;
}

void Calib::SetScaleHigh(double s, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.ScaleH=s;
    CaloCalib[cellID]=acal;
  }
  else it->second.ScaleH=s;
}

void Calib::SetScaleWidthHigh(double s, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.ScaleWidthH=s;
    CaloCalib[cellID]=acal;
  }
  else it->second.ScaleWidthH=s;
}

void Calib::SetScaleLow(double s, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.ScaleL=s;
    CaloCalib[cellID]=acal;
  }
  else it->second.ScaleL=s;
}

void Calib::SetScaleWidthLow(double s, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.ScaleWidthL=s;
    CaloCalib[cellID]=acal;
  }
  else it->second.ScaleWidthL=s;
}

void Calib::SetScaleLGHGCorr(double s, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.LGHGCorr=s;
    CaloCalib[cellID]=acal;
  }
  else it->second.LGHGCorr=s;
}

void Calib::SetScaleHGLGCorr(double s, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.HGLGCorr=s;
    CaloCalib[cellID]=acal;
  }
  else it->second.HGLGCorr=s;
}

void Calib::SetBadChannel(short s, int cellID){
  std::map<int, TileCalib>::iterator it= CaloCalib.find(cellID);
  if(it!=CaloCalib.end()){
    TileCalib acal;
    acal.BadChannel=s;
    CaloCalib[cellID]=acal;
  }
  else it->second.BadChannel=s;
}


//*****************************************************************************************
// CALIBRATION Setters by cell row, col, layer and module
//*****************************************************************************************
void Calib::SetPedestalMeanH(double ped, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetPedestalMeanH(ped,key);
}
void Calib::SetPedestalMeanL(double ped, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetPedestalMeanL(ped,key);
}
void Calib::SetPedestalSigH(double ped, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetPedestalSigH(ped,key);
}
void Calib::SetPedestalSigL(double ped, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetPedestalSigL(ped,key);
}

void Calib::SetScaleHigh(double s, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetScaleHigh(s,key);
}

void Calib::SetScaleWidthHigh(double s, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetScaleWidthHigh(s,key);
}

void Calib::SetScaleLow(double s, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetScaleLow(s,key);
}

void Calib::SetScaleWidthLow(double s, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetScaleWidthLow(s,key);
}

void Calib::SetScaleLGHGCorr(double s, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetScaleLGHGCorr(s,key);
}

void Calib::SetScaleHGLGCorr(double s, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetScaleHGLGCorr(s,key);
}

void Calib::SetBadChannel(short s, int row, int col, int lay, int mod=0){
  Setup* setup = Setup::GetInstance();
  int key=setup->GetCellID(row,col,lay,mod);
  SetBadChannel(s,key);
}


//*****************************************************************************************
// CALIBRATION Getters for global properties
//*****************************************************************************************
int Calib::GetRunNumber(void){
  return RunNumber;
}

const TTimeStamp* Calib::GetBeginRunTime(void) const{
  return &BeginRunTime;
}

double Calib::GetVop(void){
  return Vop;
}

double Calib::GetVov(void){
  return Vov;
}

bool Calib::GetBCCalib(void){
  return BCcalc;
}

//*****************************************************************************************
// CALIBRATION Setters for global properties
//*****************************************************************************************
void Calib::SetRunNumber(int r){
  RunNumber=r;
}

void Calib::SetBeginRunTime(TTimeStamp t){
  BeginRunTime=t;
}

void Calib::SetVop(double v){
  Vop=v;
}

void Calib::SetVov(double v){
  Vov=v;
}

void Calib::SetBCCalib(bool b){
  BCcalc=b;
}


void Calib::PrintGlobalInfo(){
  std::cout << "********************************************************************************************************" << std::endl;
  std::cout << "Calib info:\n \t RunNr: " << GetRunNumber() << "\t start time:" << GetBeginRunTime() << "\t Vop: " << GetVop() << "\t Vov: "<< GetVov() << "\t BC calib set: " << GetBCCalib() << std::endl;  
  std::cout << "********************************************************************************************************" << std::endl;
}


void Calib::PrintCalibToFile(TString filename){
  std::fstream fFileCalibOut;
  std::cout << "********************************************************************************************************" << std::endl;
  std::cout << "Printing calib info to: " << filename.Data() << std::endl;
  std::cout << "********************************************************************************************************" << std::endl;
  fFileCalibOut.open(filename.Data(), std::ios::out);
  fFileCalibOut << "#****************************************************************************************************************************************************************************************************************" << std::endl;
  fFileCalibOut << "#Calib info:\n \t RunNr: " << GetRunNumber() << "\t start time:" << GetBeginRunTime() << "\t Vop: " << GetVop() << "\t Vov: "<< GetVov() << "\t BC calib set: " << GetBCCalib() << std::endl;  
  fFileCalibOut << "#****************************************************************************************************************************************************************************************************************" << std::endl;
  Setup* setup = Setup::GetInstance();

  TString head = Form("#cellID\tlayer\trow\tcolumn\tmodule\tped mean H\tped sig H\tped mean L\tped sig L\tmip Scale H\tmip Width H\tmip Scale L\tmip Width L\tLG-HG\tHG-LG\tBC");  
  fFileCalibOut << head.Data() << std::endl;
  fFileCalibOut << "#****************************************************************************************************************************************************************************************************************" << std::endl;
  std::map<int, TileCalib>::const_iterator it;
  for(it=CaloCalib.begin(); it!=CaloCalib.end(); ++it){
      TString outSt = "";
      outSt = Form("%d\t%d\t%d\t%d\t%d\t%f\t%f\t%f\t%f\t%f\t%f\t%f\t%f\t%f\t%f\t%d",  
                   it->first, setup->GetLayer(it->first), setup->GetRow(it->first), setup->GetColumn(it->first), setup->GetModule(it->first), 
                   it->second.PedestalMeanH, it->second.PedestalSigH,
                   it->second.PedestalMeanL, it->second.PedestalSigL, 
                   it->second.ScaleH, it->second.ScaleWidthH,
                   it->second.ScaleL, it->second.ScaleWidthL,
                   it->second.LGHGCorr, it->second.HGLGCorr, 
                   it->second.BadChannel);
    fFileCalibOut << outSt.Data() << std::endl;
  }
  fFileCalibOut.close();
}
