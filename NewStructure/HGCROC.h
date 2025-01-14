#ifndef HGCROC_H
#define HGCROC_H

#include <vector>
#include "Tile.h"

class Hgcroc: public Tile {

 public:
  Hgcroc():Tile(ReadOut::Type::Hgcroc){}
  ~Hgcroc(){}
  std::vector<int> GetADCWaveform(void) const;
  std::vector<int> GetTOAWaveform(void) const;
  std::vector<int> GetTOTWaveform(void) const;
  int GetNsample(void) const ;
  double GetTOT(void) const;
  double GetTOA(void) const;

  void SetADCWaveform(std::vector<int>);
  void AppendWaveformADC(int);
  void ResetADCWaveformPoint(int, int);
  
  void SetTOAWaveform(std::vector<int>);
  void AppendWaveformTOA(int);
  void ResetTOAWaveformPoint(int, int);
  
  void SetTOTWaveform(std::vector<int>);
  void AppendWaveformTOT(int);
  void ResetTOTWaveformPoint(int, int);

  void SetNsample(int);
  void SetTOT(double);
  void SetTOA(double);
  
 protected:
  int Nsample;
  std::vector<int> adc_waveform;
  std::vector<int> toa_waveform;
  std::vector<int> tot_waveform;
  int TOA;
  int TOT;
  
 private:

  ClassDef(Hgcroc,1)
};


#endif
