#ifndef LFHCAL_TF1_LANGAU_EXPERIMENT_H
#define LFHCAL_TF1_LANGAU_EXPERIMENT_H

#include <TF1.h>
#include <TF1Convolution.h>
#include <TMath.h>
#include <memory>
#include <stdexcept>
#include <string>

namespace lfhcal::fft_experiment {
// This is the candidate replacement, not a production change.
// Public parameters remain [Landau width, Landau MPV, area, Gaussian sigma].
// The convolution's domain and number of samples NEVER change during a fit.
// The Gaussian is normalized and untruncated (unlike the legacy +/-5 sigma sum).
inline TF1* make(const std::string& name, double fitLo, double fitHi,
                 double convLo, double convHi, int points) {
  if (!(convLo < fitLo && fitLo < fitHi && fitHi < convHi) || points < 1000)
    throw std::invalid_argument("invalid fixed FFT domain or sample count");
  TF1 landau((name + "_landau").c_str(),
      [](double* x, double* p) {
        // ROOT's unit Landau mode is -0.22278298; p[1] denotes its MODE.
        return TMath::Landau(x[0], p[1] + 0.22278298*p[0], p[0], true);
      }, convLo, convHi, 2);
  landau.SetParameters(3., 30.);
  landau.SetParNames("LandauWidth", "LandauMPV");
  TF1 gaussian((name + "_gaussian").c_str(),
      [](double* x, double* p) { return TMath::Gaus(x[0], 0., p[0], true); },
      convLo, convHi, 1);
  gaussian.SetParameter(0, 5.);
  gaussian.SetParName(0, "GaussianSigma");
  // TF1Convolution copies its component TF1s. The shared owner also makes
  // copies of the returned TF1 safe after this factory's locals disappear.
  auto convolution = std::make_shared<TF1Convolution>(
      &landau, &gaussian, convLo, convHi, true);
  convolution->SetRange(convLo, convHi); // exact range; undo automatic 10% padding
  convolution->SetNofPointsFFT(points);
  auto f = new TF1(name.c_str(),
      [convolution](double* x, double* p) {
        const double q[3] = {p[0], p[1], p[3]};
        // Keep normalization outside the cached convolution: changing area
        // alone should not require recomputing both FFTs.
        return p[2] * (*convolution)(x, q);
      }, fitLo, fitHi, 4);
  f->SetParNames("Width", "MP", "Area", "GSigma");
  return f;
}
} // namespace lfhcal::fft_experiment
#endif
