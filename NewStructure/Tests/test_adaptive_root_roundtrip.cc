// Run --write and --read as separate processes. ROOT streams a C++-callback
// TF1 as samples: this tests plotting/evaluation after reload, not refitting a
// reloaded callback. Refitting requires constructing/rebinding the callback.
#include "LangauNumerics.h"
#include "TileSpectra.h"

#include <TDirectory.h>
#include <TFile.h>
#include <TMath.h>
#include <TNamed.h>
#include <TSystem.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
namespace langau = lfhcal::langau;

void require(bool condition, const std::string& message) {
  if (!condition) throw std::runtime_error(message);
}

double landau(double u) { return TMath::Landau(u, 0., 1.); }

struct Fixture {
  const char* name;
  std::array<double, 4> truth;
  double pedestal;
};

const std::array<Fixture, 2> fixtures{{
    {"RoundTrip", {2., 25., 20000., 5.}, 2.},
    {"NarrowRoundTrip", {0.2, 16., 18000., 5.5}, 1.}}};

langau::Parameters parameters(const std::array<double, 4>& p) {
  return {p[0], p[1], p[2], p[3]};
}

std::string metadata(const TF1& function, const TileCalib& calibration,
                     double entries) {
  std::ostringstream stream;
  stream << std::setprecision(17) << gSystem->GetPid() << '\n'
         << function.GetName() << '\n' << function.GetTitle() << '\n'
         << function.GetXmin() << ' ' << function.GetXmax() << ' '
         << function.GetNpx() << '\n';
  for (int parameter = 0; parameter != 4; ++parameter) {
    double low = 0., high = 0.;
    function.GetParLimits(parameter, low, high);
    stream << function.GetParName(parameter) << '\n'
           << function.GetParameter(parameter) << ' '
           << function.GetParError(parameter) << ' ' << low << ' ' << high
           << '\n';
  }
  stream << calibration.ScaleH << ' ' << calibration.ScaleWidthH << ' '
         << entries << '\n';
  return stream.str();
}

void write(const std::string& path) {
  const std::string mapping = path + ".mapping";
  {
    std::ofstream stream(mapping);
    require(bool(stream), "cannot create temporary mapping");
    stream << "sumOpt 2\n0 0 0 F001 1 0 0 0 0 0 5\n";
  }
  const bool initialized = Setup::GetInstance()->Initialize(mapping.c_str(), 0);
  std::filesystem::remove(mapping);
  require(initialized, "cannot initialize five-layer test mapping");
  require(Setup::GetInstance()->GetLayersInSegment(0) == 5,
          "unexpected mapping geometry");

  TFile file(path.c_str(), "RECREATE");
  require(!file.IsZombie(), "cannot create ROOT roundtrip file");
  for (const auto& fixture : fixtures) {
    TileCalib calibration;
    calibration.PedestalSigH = fixture.pedestal;
    calibration.BadChannel = 3;
    TileSpectra spectrum(fixture.name, 0, &calibration, ReadOut::Type::Hgcroc);
    TH1D* histogram = spectrum.GetHG();
    const langau::Convolution truth(parameters(fixture.truth), landau, 1e-10, 5.);
    double entries = 0.;
    for (int bin = 1; bin <= histogram->GetNbinsX(); ++bin) {
      const double count = truth(histogram->GetBinCenter(bin));
      require(std::isfinite(count) && count >= 0., "invalid Asimov count");
      histogram->SetBinContent(bin, count);
      histogram->SetBinError(bin, std::sqrt(count));
      entries += count;
    }
    histogram->SetEntries(entries);
    double result[6] = {}, errors[6] = {};
    require(spectrum.FitMipHG(result, errors, 0, 2026, true, 3.7,
                             fixture.truth[1]),
            std::string(fixture.name) + ": production fit was rejected");
    TF1* function = spectrum.GetSignalModel(1);
    require(function != nullptr, "production fit has no accepted function");
    require(std::string(function->GetTitle()).find("adaptive integration") !=
                std::string::npos,
            "production fit did not use the adaptive callback");
    require(calibration.ScaleH == result[4] &&
                calibration.ScaleWidthH == result[5] && result[5] > 0.,
            "fit did not update the calibration with its measured width");
    TDirectory* directory = file.mkdir(fixture.name);
    require(directory != nullptr, "cannot create fixture directory");
    directory->cd();
    spectrum.Write(true);
    const std::string original = metadata(*function, calibration, entries);
    TNamed expected("expected_state", original.c_str());
    require(expected.Write() > 0, "cannot write roundtrip reference state");
    std::cout << fixture.name << ": wrote " << function->GetName()
              << ", peak=" << calibration.ScaleH
              << ", FWHM=" << calibration.ScaleWidthH << '\n';
    file.cd();
  }
  file.Close();
}

void read(const std::string& path) {
  TFile file(path.c_str(), "READ");
  require(!file.IsZombie(), "cannot read ROOT roundtrip file");
  for (const auto& fixture : fixtures) {
    TDirectory* directory = file.GetDirectory(fixture.name);
    require(directory != nullptr, "missing fixture directory");
    TNamed* expected = nullptr;
    directory->GetObject("expected_state", expected);
    require(expected != nullptr, "missing pre-write reference state");
    std::istringstream stream(expected->GetTitle());
    int writer_pid = 0, npx = 0;
    double low = 0., high = 0.;
    std::string name, title;
    stream >> writer_pid >> std::ws;
    std::getline(stream, name);
    std::getline(stream, title);
    stream >> low >> high >> npx;
    require(writer_pid != gSystem->GetPid(), "reader must use a fresh process");
    TF1* function = nullptr;
    directory->GetObject(name.c_str(), function);
    require(function != nullptr, "missing saved production TF1 " + name);
    require(name == function->GetName() && title == function->GetTitle(),
            "function name/title changed after ROOT roundtrip");
    // Semicolons in a ROOT title become axis labels; numerical provenance
    // must remain metadata rather than relabeling ADC and histogram counts.
    const auto* drawing = function->GetHistogram();
    require(drawing != nullptr &&
                std::string(drawing->GetXaxis()->GetTitle()).empty() &&
                std::string(drawing->GetYaxis()->GetTitle()).empty(),
            "adaptive metadata must not become plot axis labels");
    require(function->GetNpar() == 4 && function->GetNpx() == npx && npx == 1000,
            "function parameter/sample count changed after ROOT roundtrip");
    require(function->GetXmin() == low && function->GetXmax() == high,
            "function range changed after ROOT roundtrip");
    std::array<double, 4> fitted{};
    for (int parameter = 0; parameter != 4; ++parameter) {
      std::string parameter_name;
      double error = 0., limit_low = 0., limit_high = 0.;
      stream >> std::ws;
      std::getline(stream, parameter_name);
      stream >> fitted[parameter] >> error >> limit_low >> limit_high;
      double saved_low = 0., saved_high = 0.;
      function->GetParLimits(parameter, saved_low, saved_high);
      require(parameter_name == function->GetParName(parameter) &&
                  fitted[parameter] == function->GetParameter(parameter) &&
                  error == function->GetParError(parameter) &&
                  limit_low == saved_low && limit_high == saved_high,
              "parameter metadata changed after ROOT roundtrip");
    }
    double peak = 0., width = 0., entries = 0.;
    stream >> peak >> width >> entries;
    require(bool(stream), "malformed pre-write reference state");
    require(std::isfinite(peak) && std::isfinite(width) && width > 0.,
            "invalid pre-write peak/FWHM");
    TH1D* histogram = nullptr;
    const std::string histogram_name =
        std::string("hspectra") + fixture.name + "ADCCellID0";
    directory->GetObject(histogram_name.c_str(), histogram);
    require(histogram != nullptr && histogram->GetEntries() == entries,
            "production source histogram was not preserved");

    // Check bin centers as downstream analyses do, and points deliberately
    // between the TF1 sampling grid. Compare absolute error with peak height:
    // a relative error at vanishing tail values is not a useful plot criterion.
    const langau::Convolution accurate(parameters(fitted), landau, 1e-12, 5.);
    std::vector<double> x_values{low, high, peak};
    for (int bin = 1; bin <= histogram->GetNbinsX(); ++bin) {
      const double x = histogram->GetBinCenter(bin);
      if (x >= low && x <= high) x_values.push_back(x);
    }
    for (int interval = 0; interval != npx; ++interval) {
      for (double fraction : {0.37, 0.5}) {
        x_values.push_back(low + (high - low) * (interval + fraction) / npx);
      }
    }
    double height = 0., maximum_error = 0., worst_x = 0.;
    for (double x : x_values) {
      const double reference = accurate(x);
      const double saved = function->Eval(x);
      require(std::isfinite(reference) && reference >= 0. &&
                  std::isfinite(saved) && saved >= 0.,
              "nonfinite/negative curve after ROOT roundtrip");
      height = std::max(height, reference);
      const double error = std::abs(saved - reference);
      if (error > maximum_error) {
        maximum_error = error;
        worst_x = x;
      }
    }
    require(height > 0., "empty reloaded curve");
    const double relative_height_error = maximum_error / height;
    std::cout << std::setprecision(12) << fixture.name << ": "
              << x_values.size() << " saved-curve checks, max |error|/height="
              << relative_height_error << " at x=" << worst_x << '\n';
    require(relative_height_error < 1e-3,
            "reloaded TF1 interpolation exceeds 0.1% of peak height");
  }
  std::cout << "ROOT preserves sampled curves and fit metadata; a saved C++ "
               "callback must be rebound before parameter changes/refitting.\n";
}
}  // namespace

int main(int argc, char** argv) {
  try {
    require(argc == 3, "usage: test_adaptive_root_roundtrip --write|--read FILE");
    const std::string mode = argv[1];
    if (mode == "--write") write(argv[2]);
    else if (mode == "--read") read(argv[2]);
    else throw std::runtime_error("unknown mode " + mode);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "adaptive ROOT roundtrip: " << error.what() << '\n';
    return 1;
  }
}
