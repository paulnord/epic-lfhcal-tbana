#include "TileSpectra.h"
#include "Setup.h"

#include "Math/MinimizerOptions.h"
#include "TMath.h"
#include "TROOT.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace {
void require(bool condition, const std::string &message) {
  if (!condition) throw std::runtime_error(message);
}

void near(double actual, double expected, double tolerance, const std::string &name) {
  require(std::isfinite(actual) && std::abs(actual - expected) <= tolerance,
          name + ": expected " + std::to_string(expected) + ", got " +
              std::to_string(actual));
}

// The fixture uses a dense midpoint integral, independent of the adaptive
// implementation being tested. At these moderate scale ratios 4,000 points
// resolve the convolution comfortably; no random event generation is involved.
double reference_density(double x, const std::array<double, 4> &p) {
  constexpr int points = 4000;
  const double location = p[1] + 0.22278298 * p[0];
  const double low = x - 5 * p[3], step = 10 * p[3] / points;
  double sum = 0;
  for (int i = 0; i < points; ++i) {
    const double t = low + (i + 0.5) * step;
    const double z = (x - t) / p[3];
    sum += TMath::Landau(t, location, p[0]) / p[0] * std::exp(-0.5 * z * z);
  }
  return p[2] * step * sum / (p[3] * std::sqrt(2 * std::acos(-1.0)));
}

void fill_asimov(TH1D &histogram, const std::array<double, 4> &parameters) {
  double entries = 0;
  for (int bin = 1; bin <= histogram.GetNbinsX(); ++bin) {
    const double value = reference_density(histogram.GetBinCenter(bin), parameters);
    histogram.SetBinContent(bin, value);
    histogram.SetBinError(bin, std::sqrt(value));
    entries += value;
  }
  histogram.SetEntries(entries);
}

struct MappingFixture {
  std::filesystem::path path = std::filesystem::temp_directory_path() /
      ("lfhcal-adaptive-fit-mapping-" + std::to_string(
          std::chrono::steady_clock::now().time_since_epoch().count()) + ".txt");
  MappingFixture() {
    std::ofstream file(path);
    file << "sumOpt 2\n0 0 0 F001 1 0 0 0 0 0 5\n";
    file.close();
    require(bool(file), "write test mapping");
    require(Setup::GetInstance()->Initialize(path.c_str(), 0), "initialize test mapping");
    require(Setup::GetInstance()->GetLayersInSegment(0) == 5,
            "fixture uses five-layer HGCROC segment");
  }
  ~MappingFixture() { std::error_code error; std::filesystem::remove(path, error); }
};

void expect_rejected(TileSpectra &spectra, TileCalib &calibration,
                     const std::string &reason, double avmip = 25,
                     double vov = 3.7) {
  const double old_peak = calibration.ScaleH, old_width = calibration.ScaleWidthH;
  std::array<double, 6> out, error;
  out.fill(-9876.5);
  error.fill(-8765.5);
  require(!spectra.FitMipHG(out.data(), error.data(), 0, 2026, true, vov, avmip),
          reason + " must reject fit");
  require(spectra.GetSignalModel(1) == nullptr,
          reason + " must not expose a stale signal model");
  require(calibration.ScaleH == old_peak && calibration.ScaleWidthH == old_width,
          reason + " must retain preceding calibration");
  require(std::all_of(out.begin(), out.end(), [](double x) { return x == -9876.5; }) &&
          std::all_of(error.begin(), error.end(), [](double x) { return x == -8765.5; }),
          reason + " must not publish partial fit outputs");
}

void test_hgcroc() {
  TileCalib calibration;
  calibration.PedestalSigH = 2;
  calibration.BadChannel = 3;
  calibration.ScaleH = 123;
  calibration.ScaleWidthH = 456;
  calibration.ScaleL = 789;
  TileSpectra spectra("AdaptiveRegression", 0, &calibration, ReadOut::Type::Hgcroc);
  const std::array<double, 4> truth{{2, 25, 20000, 5}};
  fill_asimov(*spectra.GetHG(), truth);
  std::array<double, 6> out{}, error{};
  require(spectra.FitMipHG(out.data(), error.data(), 0, 2026, true, 3.7, 25),
          "HGCROC adaptive fit of known smooth spectrum must succeed");
  TF1 *model = spectra.GetSignalModel(1);
  require(model != nullptr, "successful HGCROC model is available");
  near(out[0], truth[0], 0.03, "HGCROC recovered Landau width");
  near(out[1], truth[1], 0.03, "HGCROC recovered MP");
  near(out[2], truth[2], 60, "HGCROC recovered area");
  near(out[3], truth[3], 0.03, "HGCROC recovered Gaussian sigma");
  // Independently recorded high-resolution values for the fixture parameters.
  near(out[4], 26.947818001957465, 0.03, "HGCROC recovered peak");
  near(out[5], 15.868980470113456, 0.06, "HGCROC recovered FWHM");
  require(calibration.ScaleH == out[4] && calibration.ScaleWidthH == out[5],
          "successful HGCROC fit commits checked peak and FWHM");
  require(calibration.ScaleL == 789, "HG fit preserves LG calibration");
  require(std::all_of(error.begin(), error.end(), [](double x) { return std::isfinite(x); }),
          "successful HGCROC errors and fit diagnostics are finite");
  for (double x : {18.5, 25.5, 35.5, 60.5}) {
    const double expected = reference_density(x, truth);
    near(model->Eval(x), expected, 0.003 * expected,
         "HGCROC fitted curve recovers synthetic signal");
  }

  // Inspect the actual callback selected by FitMipHG at a scale ratio where
  // the old fixed rule is badly aliased. Frozen high-accuracy reference values
  // make this a routing regression as well as a convergence test.
  model->SetParameters(0.02, 300, 20000, 30);
  near(model->Eval(299.5), 265.67836730834824, 1e-7,
       "HGCROC callback resolves narrow Landau core");
  near(model->Eval(300), 265.7363953607449, 1e-7,
       "HGCROC callback uses adaptive convolution");
  model->SetParameters(out.data());

  // Reusing an object that previously succeeded exercises stale-model state.
  calibration.BadChannel = 1;
  expect_rejected(spectra, calibration, "masked channel");
  calibration.BadChannel = 3;
  for (double invalid : {0.0, -1.0, std::numeric_limits<double>::quiet_NaN()}) {
    calibration.PedestalSigH = invalid;
    expect_rejected(spectra, calibration, "invalid pedestal sigma");
  }
  calibration.PedestalSigH = 2;
  for (double invalid : {0.0, -1.0, std::numeric_limits<double>::quiet_NaN(),
                         std::numeric_limits<double>::infinity()}) {
    expect_rejected(spectra, calibration, "invalid improved-fit seed/range", invalid);
  }
  expect_rejected(spectra, calibration, "nonfinite voltage", 25,
                  std::numeric_limits<double>::quiet_NaN());
  const int signal_bin = spectra.GetHG()->FindBin(25.0);
  const double original = spectra.GetHG()->GetBinContent(signal_bin);
  for (double invalid : {std::numeric_limits<double>::quiet_NaN(),
                         std::numeric_limits<double>::infinity(),
                         2.0 * std::numeric_limits<int>::max()}) {
    spectra.GetHG()->SetBinContent(signal_bin, invalid);
    expect_rejected(spectra, calibration, "invalid/nonrepresentable fit integral");
  }
  spectra.GetHG()->SetBinContent(signal_bin, original);

  // The initial HGCROC calibration stage also uses the adaptive callback,
  // retaining its own original range, bounds and non-improved fit option.
  require(spectra.FitMipHG(out.data(), error.data(), 0, 2026, false, 3.7, 25),
          "initial HGCROC fit must succeed after preceding failures");
  near(out[1], truth[1], 0.03, "initial HGCROC recovered MP");
  near(out[4], 26.947818001957465, 0.03, "initial HGCROC recovered peak");
  near(out[5], 15.868980470113456, 0.06, "initial HGCROC recovered FWHM");
}

void test_caen_legacy_route() {
  TileCalib calibration;
  calibration.PedestalSigH = 30;
  calibration.BadChannel = 3;
  TileSpectra spectra("LegacyRegression", 0, &calibration, ReadOut::Type::Caen);
  const std::array<double, 4> truth{{50, 300, 200000, 30}};
  fill_asimov(*spectra.GetHG(), truth);
  std::array<double, 6> out{}, error{};
  require(spectra.FitMipHG(out.data(), error.data(), 0, 2026, true, 3.7, 300),
          "CAEN HG fit remains successful");
  TF1 *model = spectra.GetSignalModel(1);
  require(model != nullptr, "successful CAEN model is available");
  near(out[0], truth[0], 0.3, "CAEN recovered Landau width");
  near(out[1], truth[1], 0.3, "CAEN recovered MP");
  near(out[3], truth[3], 0.3, "CAEN recovered Gaussian sigma");

  // The fitted callback must remain the historical 100-point evaluator. This
  // deliberately narrow diagnostic vector distinguishes it from adaptive
  // integration. These values were frozen from the pre-change legacy formula;
  // it is not a proposed physical fit or a new calibration.
  model->SetParameters(0.02, 300, 20000, 30);
  const std::array<double, 7> x{{250, 290, 299.5, 300, 300.5, 310, 350}};
  const std::array<double, 7> legacy{{
      0.7556509447685021, 74.4076981686752, 19.865750526032386,
      9.287696865932999, 5.581889675979586, 3.8089326804194514,
      20.649295812095065}};
  for (std::size_t i = 0; i < x.size(); ++i)
    near(model->Eval(x[i]), legacy[i], 1e-11 * std::max(1.0, legacy[i]),
         "CAEN keeps legacy convolution callback");
}
} // namespace

int main() {
  try {
    gROOT->SetBatch(true);
    ROOT::Math::MinimizerOptions::SetDefaultMinimizer("Minuit2", "Migrad");
    MappingFixture mapping;
    test_hgcroc();
    test_caen_legacy_route();
    std::cout << "TileSpectra adaptive HGCROC and legacy CAEN regressions passed\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "TileSpectra regression failed: " << error.what() << '\n';
    return 1;
  }
}
