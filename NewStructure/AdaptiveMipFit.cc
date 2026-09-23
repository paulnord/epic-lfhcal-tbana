#include "AdaptiveMipFit.h"
#include "TileSpectra.h"
#include "LangauNumerics.h"
#include "TFitResult.h"
#include "TFitResultPtr.h"
#include "Math/MinimizerOptions.h"
#include "TMath.h"
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace {
constexpr double kLangauIntegrationTolerance = 1e-10;
constexpr double kLangauGaussianSpan = 5.0;
const char *kAdaptiveLangauTitle =
    "Landau-Gaussian (adaptive integration, rtol=1e-10, span=5)";

double adaptiveLangau(double *x, double *par) {
  return lfhcal::langau::Convolution(
      {par[0], par[1], par[2], par[3]},
      [](double u) { return TMath::Landau(u, 0., 1.); },
      kLangauIntegrationTolerance, kLangauGaussianSpan)(x[0]);
}
}

namespace lfhcal::adaptive {

bool fitMipHG(TileSpectra& self, double* out, double* outErr,
              int verbosity, int year, bool impE, double vov, double avmip) {
  Setup* setupT = Setup::GetInstance();
  self.bmipHG = false;

  if (!std::isfinite(self.calib->PedestalSigH) || self.calib->PedestalSigH <= 0 ||
      !std::isfinite(vov) || (impE && !std::isfinite(avmip))) {
    std::cerr << "Skipped HG cell " << self.cellID
              << " adaptive setup failed: invalid pedestal or fit seed" << std::endl;
    return false;
  }

  double fitrange[2];
  self.GetFitRange(fitrange, year, true, impE, vov, avmip);
  if (!std::isfinite(fitrange[0]) || !std::isfinite(fitrange[1]) ||
      fitrange[0] >= fitrange[1]) {
    std::cerr << "Skipped HG cell " << self.cellID
              << " adaptive setup failed: invalid fit interval" << std::endl;
    return false;
  }

  double intArea = self.hspectraHG.Integral(self.hspectraHG.FindBin(fitrange[0]),
                                            self.hspectraHG.FindBin(fitrange[1]));
  if (!std::isfinite(intArea) || intArea < 1 ||
      intArea > std::numeric_limits<int>::max()) {
    std::cerr << "Skipped HG cell " << self.cellID
              << " adaptive setup failed: invalid fit integral" << std::endl;
    return false;
  }
  double intNoise = self.hspectraHG.Integral(
      self.hspectraHG.FindBin(-2 * self.calib->PedestalSigH),
      self.hspectraHG.FindBin(+2 * self.calib->PedestalSigH));
  double intAN3s = self.hspectraHG.Integral(
      self.hspectraHG.FindBin(+3 * self.calib->PedestalSigH),
      self.hspectraHG.FindBin(fitrange[1]));
  if (intArea / intNoise < 1e-5 && intAN3s > 200) {
    if (verbosity > 0)
      std::cout << "==========> Skipped HG cell " << self.cellID
                << " S/B too small!" << std::endl;
    return false;
  }

  double startvalues[4], parlimitslo[4], parlimitshi[4];
  self.SetParametersFitHG(startvalues, parlimitslo, parlimitshi,
                          intArea, year, impE, vov, avmip);
  for (int i = 0; i < 4; ++i) {
    if (!std::isfinite(parlimitslo[i]) || !std::isfinite(parlimitshi[i]) ||
        parlimitslo[i] >= parlimitshi[i]) {
      std::cerr << "Skipped HG cell " << self.cellID
                << " adaptive setup failed: invalid parameter bounds" << std::endl;
      return false;
    }
  }
  try {
    adaptiveLangau(&startvalues[1], startvalues);
  } catch (const std::exception& error) {
    std::cerr << "Skipped HG cell " << self.cellID
              << " adaptive setup failed: " << error.what() << std::endl;
    return false;
  }

  if (verbosity > 1) {
    std::cout << "Layer: " << setupT->GetLayer(self.cellID) << std::endl;
    std::cout << "Fit range: " << fitrange[0] << "\t" << fitrange[1] << std::endl;
    for (int i = 0; i < 4; ++i)
      std::cout << "parameter " << i << ": " << startvalues[i] << "\t"
                << parlimitslo[i] << "\t" << parlimitshi[i] << std::endl;
  }

  TString funcName = Form("fmip%sHGCellID%d", self.TileName.Data(), self.cellID);
  self.SignalHG = TF1(funcName.Data(), adaptiveLangau, fitrange[0], fitrange[1], 4);
  self.SignalHG.SetTitle(kAdaptiveLangauTitle);
  self.SignalHG.SetNpx(1000);
  self.SignalHG.SetParameters(startvalues);
  self.SignalHG.SetParNames("Width", "MP", "Area", "GSigma");
  for (int i = 0; i < 4; ++i)
    self.SignalHG.SetParLimits(i, parlimitslo[i], parlimitshi[i]);

  TString fitOption = impE ? "QRLMN0" : "QRLN0";
  if (verbosity > 2) fitOption = impE ? "RVLMN0" : "RLN0";
  ROOT::Math::MinimizerOptions::SetDefaultMaxFunctionCalls(1000);
  ROOT::Math::MinimizerOptions::SetDefaultMaxIterations(100);
  if (verbosity > 2) ROOT::Math::MinimizerOptions::SetDefaultPrintLevel(3);

  int fitStatus;
  try {
    fitStatus = self.hspectraHG.Fit(&self.SignalHG, fitOption);
  } catch (const std::exception& error) {
    std::cerr << "Skipped HG cell " << self.cellID
              << " adaptive fit failed: " << error.what() << std::endl;
    return false;
  }
  if (!self.SignalHG.IsValid()) return false;
  int limitStatus = 0;
  for (int i = 0; i < 4; ++i) {
    if (TMath::Abs(self.SignalHG.GetParameter(i) - parlimitslo[i]) < 1e-5 ||
        TMath::Abs(self.SignalHG.GetParameter(i) - parlimitshi[i]) < 1e-5) {
      ++limitStatus;
      if (verbosity > 0)
        std::cout << i << "\t" << self.SignalHG.GetParameter(i) << "\t : \t"
                  << parlimitslo[i] << "\t" << parlimitshi[i] << "\t layer: "
                  << setupT->GetLayer(self.cellID) << std::endl;
    }
  }
  if (verbosity > 1)
    std::cout << "Fit status HG " << self.cellID << "\t" << fitStatus
              << "\t limit reached: " << limitStatus << std::endl;
  if (!(fitStatus == 4000 || fitStatus == 0 || fitStatus == 4070 || fitStatus == 70)) {
    if (verbosity > 0)
      std::cout << "==========> Skipped HG cell " << self.cellID
                << " fit failed" << std::endl;
    return false;
  }
  if (limitStatus > 0) {
    if (verbosity > 0)
      std::cout << "==========> Skipped HG cell " << self.cellID
                << " too many limits reached" << std::endl;
    return false;
  }

  double fitted[4];
  self.SignalHG.GetParameters(fitted);
  std::vector<double> centres;
  for (int bin = 1; bin <= self.hspectraHG.GetNbinsX(); ++bin) {
    double x = self.hspectraHG.GetBinCenter(bin);
    if (x >= fitrange[0] && x <= fitrange[1]) centres.push_back(x);
  }
  const auto check = lfhcal::langau::verify(
      {fitted[0], fitted[1], fitted[2], fitted[3]},
      [](double u) { return TMath::Landau(u, 0., 1.); },
      kLangauIntegrationTolerance, centres);
  if (!check.complete || !check.pass) {
    std::cerr << "Skipped HG cell " << self.cellID
              << " adaptive peak/FWHM failed: " << check.error << std::endl;
    return false;
  }

  for (int i = 0; i < 4; ++i) {
    out[i] = fitted[i];
    outErr[i] = self.SignalHG.GetParError(i);
  }
  outErr[4] = self.SignalHG.GetChisquare();
  outErr[5] = self.SignalHG.GetNDF();
  self.calib->ScaleH = out[4] = check.curve.peak;
  self.calib->ScaleWidthH = out[5] = check.curve.fwhm;
  self.bmipHG = true;
  return true;
}

}  // namespace lfhcal::adaptive
