#ifndef LFHCAL_TF1_LANGAU_EXPERIMENT_H
#define LFHCAL_TF1_LANGAU_EXPERIMENT_H

#include <TF1.h>
#include <TF1Convolution.h>
#include <TMath.h>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>

namespace lfhcal::fft_experiment {
// Candidate replacement, not a production change. Public parameters remain
// [Landau width, Landau MPV, area, Gaussian sigma]. Domain/grid stay fixed.
inline TF1* make(const std::string& name, double fitLo, double fitHi,
                 double convLo, double convHi, int points) {
  if (!(convLo < fitLo && fitLo < fitHi && fitHi < convHi) || points < 1000)
    throw std::invalid_argument("invalid fixed FFT domain or sample count");
  // ROOT TF1Convolution implementations normalize by (fNofPoints*fNofPoints)
  // with Int_t operands. Guard the PRODUCT without overflowing it ourselves.
  // On a 32-bit Int_t, 46340 is the largest safe count. Even if a later ROOT
  // release fixes that expression, this conservative experiment remains safe.
  if (points > std::numeric_limits<Int_t>::max()/points)
    throw std::invalid_argument("FFT count squared exceeds Int_t; use <=46340 points");
  TF1 landau((name + "_landau").c_str(),
      [](double* x, double* p) {
        return TMath::Landau(x[0], p[1] + 0.22278298*p[0], p[0], true);
      }, convLo, convHi, 2);
  landau.SetParameters(3., 30.);
  landau.SetParNames("LandauWidth", "LandauMPV");
  TF1 gaussian((name + "_gaussian").c_str(),
      [](double* x, double* p) { return TMath::Gaus(x[0], 0., p[0], true); },
      convLo, convHi, 1);
  gaussian.SetParameter(0, 5.);
  gaussian.SetParName(0, "GaussianSigma");
  auto convolution = std::make_shared<TF1Convolution>(
      &landau, &gaussian, convLo, convHi, true);
  convolution->SetRange(convLo, convHi); // undo automatic 10% padding
  convolution->SetNofPointsFFT(points);
  auto f = new TF1(name.c_str(),
      [convolution](double* x, double* p) {
        const double q[3] = {p[0], p[1], p[3]};
        return p[2] * (*convolution)(x, q);
      }, fitLo, fitHi, 4);
  f->SetParNames("Width", "MP", "Area", "GSigma");
  return f;
}
} // namespace lfhcal::fft_experiment
#endif
