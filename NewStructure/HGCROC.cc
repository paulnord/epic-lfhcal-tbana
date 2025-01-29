#include "HGCROC.h"
#include <cassert>
ClassImp(Hgcroc)
std::vector<int> Hgcroc::GetADCWaveform(void) const{
  return adc_waveform;
}

std::vector<int> Hgcroc::GetTOAWaveform(void) const{
  return toa_waveform;
}

std::vector<int> Hgcroc::GetTOTWaveform(void) const{
  return tot_waveform;
}

int Hgcroc::GetNsample(void) const{
  return Nsample;
}

double Hgcroc::GetTOT(void) const{
  return TOT;
}

double Hgcroc::GetTOA(void) const{
  return TOA;
}

int Hgcroc::GetPedestal(void) const{
  return pedestal;
}

void Hgcroc::SetADCWaveform(std::vector<int> v){
  adc_waveform=v;
}

void Hgcroc::AppendWaveformADC(int a){
  adc_waveform.push_back(a);
}

void Hgcroc::ResetADCWaveformPoint(int s, int a){
  assert(0<=s && s<(int)adc_waveform.size());
  adc_waveform.at(s)=a;
}

void Hgcroc::SetTOAWaveform(std::vector<int> v){
  toa_waveform=v;
}

void Hgcroc::AppendWaveformTOA(int a){
  toa_waveform.push_back(a);
}

void Hgcroc::ResetTOAWaveformPoint(int s, int a){
  assert(0<=s && s<(int)toa_waveform.size());
  toa_waveform.at(s)=a;
}

void Hgcroc::SetTOTWaveform(std::vector<int> v){
  tot_waveform=v;
}

void Hgcroc::AppendWaveformTOT(int a){
  tot_waveform.push_back(a);
}

void Hgcroc::ResetTOTWaveformPoint(int s, int a){
  assert(0<=s && s<(int)tot_waveform.size());
  tot_waveform.at(s)=a;
}

void Hgcroc::SetNsample(int n){
  Nsample=n;
}

void Hgcroc::SetTOT(double tot){
  TOT=tot;
}

void Hgcroc::SetTOA(double toa){
  TOA=toa;
}

void Hgcroc::SetPedestal(int ped){
  pedestal=ped;
}