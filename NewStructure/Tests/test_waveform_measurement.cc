#include "TileSpectra.h"

#include "TProfile.h"

#include <cmath>
#include <iostream>
#include <string>

namespace {
int failures = 0;

void Check(bool condition, const std::string& message){
  if (!condition){
    std::cerr << "FAIL: " << message << '\n';
    ++failures;
  }
}

void CheckNear(double actual, double expected, double tolerance,
               const std::string& message){
  Check(std::isfinite(actual) && std::fabs(actual-expected) <= tolerance,
        message+" (actual="+std::to_string(actual)+
        ", expected="+std::to_string(expected)+")");
}

TProfile MakeProfile(const char* name, const double* values, int n){
  TProfile profile(name,"",n,0.,static_cast<double>(n));
  for (int i = 0; i < n; ++i) profile.Fill(i+0.5,values[i]);
  profile.SetDirectory(nullptr);
  return profile;
}
}

int main(){
  {
    const double values[] = {0.,2.,6.,10.,6.,2.,0.};
    TProfile profile = MakeProfile("ari",values,7);
    const WaveformMeasurement m = TileSpectra::MeasureWaveform(&profile,200.,false);
    Check(m.status == WaveformMeasurementStatus::Valid,"Ari mode accepts a bounded pulse");
    CheckNear(m.amplitude,10.,1e-12,"peak amplitude uses maximum bin content");
    CheckNear(m.peakTime,3.5,1e-12,"peak time uses the maximum bin center");
    CheckNear(m.fwhm,4.,1e-12,"Ari FWHM uses below-half bin centers");

    const WaveformMeasurement interpolated = TileSpectra::MeasureWaveform(&profile,200.,true);
    CheckNear(interpolated.fwhm,2.5,1e-12,"interpolated mode remains explicitly distinct");
  }

  {
    const double values[] = {2.,6.,10.,4.,8.,3.,0.};
    TProfile profile = MakeProfile("multiple",values,7);
    const WaveformMeasurement m = TileSpectra::MeasureWaveform(&profile,200.,false);
    Check(m.status == WaveformMeasurementStatus::Valid,"multiple crossings remain deterministic");
    Check(m.leftBin == 1 && m.rightBin == 4,
          "nearest at-or-below-half bins are selected around the first strict maximum");
  }

  {
    const double values[] = {5.,5.,5.,5.,5.};
    TProfile profile = MakeProfile("flat",values,5);
    const WaveformMeasurement m = TileSpectra::MeasureWaveform(&profile,200.,false);
    Check(m.hasPeak,"positive flat waveform retains Ari's first-bin peak");
    Check(!m.hasFWHM && m.status == WaveformMeasurementStatus::MissingBothCrossings,
          "flat waveform reports an undefined width instead of zero");
    Check(std::isnan(m.fwhm),"undefined width is NaN");
  }

  {
    const double values[] = {0.,1.,4.,8.,9.};
    TProfile profile = MakeProfile("boundary",values,5);
    const WaveformMeasurement m = TileSpectra::MeasureWaveform(&profile,200.,false);
    Check(m.hasPeak && m.peakAtSearchBoundary,"boundary peak is explicitly flagged");
    Check(!m.hasFWHM && m.status == WaveformMeasurementStatus::MissingRightCrossing,
          "boundary pulse reports the missing right crossing");
  }

  {
    const double values[] = {0.,0.,0.,0.,0.};
    TProfile profile = MakeProfile("empty",values,5);
    const WaveformMeasurement m = TileSpectra::MeasureWaveform(&profile,200.,false);
    Check(!m.hasPeak && m.status == WaveformMeasurementStatus::NoFinitePositivePeak,
          "zero waveform is invalid rather than a zero-valued measurement");
  }

  {
    TProfile profile("cutoff","",220,0.,220.);
    for (int bin = 1; bin <= 220; ++bin){
      double value = 0.;
      if (bin == 19 || bin == 23) value = 2.;
      if (bin == 20 || bin == 22) value = 6.;
      if (bin == 21) value = 10.;
      if (bin == 211) value = 100.;
      profile.Fill(bin-0.5,value);
    }
    profile.SetDirectory(nullptr);
    const WaveformMeasurement m = TileSpectra::MeasureWaveform(&profile,200.,false);
    CheckNear(m.amplitude,10.,1e-12,"peak search ignores a larger post-200 ns value");
    CheckNear(m.peakTime,20.5,1e-12,"peak search keeps Ari's inclusive FindBin cutoff");
    CheckNear(m.fwhm,4.,1e-12,"cutoff case retains Ari's bin-center width");
  }

  return failures == 0 ? 0 : 1;
}
