#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "TFile.h"
#include "TF1.h"
#include "TH1.h"
#include "TMath.h"
#include "Math/MinimizerOptions.h"

namespace {

double langaufun(double *x, double *par) {
  static double invsq2pi = 0.3989422804014;
  static double mpshift = -0.22278298;
  static double np = 100.0;
  static double sc = 5.0;

  double sum = 0.0;
  double mpc = par[1] - mpshift * par[0];
  double xlow = x[0] - sc * par[3];
  double xupp = x[0] + sc * par[3];
  double step = (xupp - xlow) / np;

  for (double i = 1.0; i <= np / 2; ++i) {
    double xx = xlow + (i - .5) * step;
    double fland = TMath::Landau(xx, mpc, par[0]) / par[0];
    sum += fland * TMath::Gaus(x[0], xx, par[3]);

    xx = xupp - (i - .5) * step;
    fland = TMath::Landau(xx, mpc, par[0]) / par[0];
    sum += fland * TMath::Gaus(x[0], xx, par[3]);
  }

  return par[2] * step * sum * invsq2pi / par[3];
}

int langaupro(double *params, double &maxx, double &fwhm) {
  double p, x, fy, fxr, fxl;
  double step;
  double l, lold;
  int i = 0;
  const int maxcalls = 10000;

  p = params[1] - 0.1 * params[0];
  step = 0.05 * params[0];
  lold = -2.0;
  l = -1.0;

  while ((l != lold) && (i < maxcalls)) {
    ++i;
    lold = l;
    x = p + step;
    l = langaufun(&x, params);
    if (l < lold) step = -step / 10;
    p += step;
  }
  if (i == maxcalls) return -1;

  maxx = x;
  fy = l / 2;

  p = maxx + params[0];
  step = params[0];
  lold = -2.0;
  l = -1e300;
  i = 0;

  while ((l != lold) && (i < maxcalls)) {
    ++i;
    lold = l;
    x = p + step;
    l = TMath::Abs(langaufun(&x, params) - fy);
    if (l > lold) step = -step / 10;
    p += step;
  }
  if (i == maxcalls) return -2;
  fxr = x;

  p = maxx - 0.5 * params[0];
  step = -params[0];
  lold = -2.0;
  l = -1e300;
  i = 0;

  while ((l != lold) && (i < maxcalls)) {
    ++i;
    lold = l;
    x = p + step;
    l = TMath::Abs(langaufun(&x, params) - fy);
    if (l > lold) step = -step / 10;
    p += step;
  }
  if (i == maxcalls) return -3;

  fxl = x;
  fwhm = fxr - fxl;
  return 0;
}

struct Seed {
  std::string label;
  double avmip = 0.0;
  double ped_sigma = 0.581290;
  int active_channels = -1;
};

struct Config {
  std::string input;
  std::string hist_path;
  int cell = 903;
  int layers_in_segment = 8;
  double vov = 5.7;
  std::string fit_option = "QRLMN0";
  int repeat = 1;

  std::vector<std::string> calib_files;
  std::vector<double> avmips;
  std::optional<double> scan_start;
  std::optional<double> scan_stop;
  std::optional<double> scan_step;

  std::optional<double> ped_sigma;
  std::optional<double> fit_low;
  std::optional<double> fit_high;
  std::optional<double> start_mp;
  std::optional<double> mp_low;
  std::optional<double> mp_high;
};

[[noreturn]] void usage(const char *argv0, int code = 2) {
  std::ostream &out = code == 0 ? std::cout : std::cerr;
  out
      << "Usage: " << argv0 << " INPUT.root [options]\n\n"
      << "Fit the isolated cell-903 MIP histogram with the same Landau-Gaussian\n"
      << "function, start values, limits, Minuit2/Migrad choice, and ROOT fit\n"
      << "options used by LFHCal GetImprovedScaling/FitMipHG.\n\n"
      << "Seed options (may be repeated):\n"
      << "  --calib FILE          derive avmip and cell pedestal sigma from a prior calib\n"
      << "  --avmip X             fit one explicit average-MIP seed\n"
      << "  --scan A B STEP       scan avmip from A through B inclusive\n\n"
      << "Fit controls:\n"
      << "  --hist PATH           histogram path (auto-detected by default)\n"
      << "  --cell N              target cell, default 903\n"
      << "  --ped-sigma X         override pedestal sigma\n"
      << "  --layers N            layers in segment, default 8 (>5 production branch)\n"
      << "  --vov X               overvoltage, default 5.7 V\n"
      << "  --fit-option OPT      ROOT TH1::Fit option, default QRLMN0\n"
      << "  --repeat N            repeat each identical fit N times\n"
      << "  --fit-low X           override production-derived lower fit edge\n"
      << "  --fit-high X          override production-derived upper fit edge\n"
      << "  --start-mp X          override MP starting value\n"
      << "  --mp-low X            override MP lower parameter limit\n"
      << "  --mp-high X           override MP upper parameter limit\n"
      << "  -h, --help            show this help\n\n"
      << "If neither --calib, --avmip, nor --scan is supplied, two seeds inferred\n"
      << "from the stored refine2/refine3 TF1 ranges are used:\n"
      << "  52.10410788425 and 52.09756765275\n";
  std::exit(code);
}

double parse_double(const std::string &text, const std::string &name) {
  size_t used = 0;
  double value = 0.0;
  try {
    value = std::stod(text, &used);
  } catch (const std::exception &) {
    throw std::runtime_error("invalid " + name + ": " + text);
  }
  if (used != text.size() || !std::isfinite(value)) {
    throw std::runtime_error("invalid " + name + ": " + text);
  }
  return value;
}

int parse_int(const std::string &text, const std::string &name) {
  size_t used = 0;
  long value = 0;
  try {
    value = std::stol(text, &used);
  } catch (const std::exception &) {
    throw std::runtime_error("invalid " + name + ": " + text);
  }
  if (used != text.size()) throw std::runtime_error("invalid " + name + ": " + text);
  return static_cast<int>(value);
}

Config parse_args(int argc, char **argv) {
  if (argc < 2) usage(argv[0]);

  Config c;
  c.input = argv[1];

  auto need = [&](int &i, const char *opt) -> std::string {
    if (i + 1 >= argc) throw std::runtime_error(std::string("missing value for ") + opt);
    return argv[++i];
  };

  for (int i = 2; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "-h" || arg == "--help") usage(argv[0], 0);
    else if (arg == "--hist") c.hist_path = need(i, "--hist");
    else if (arg == "--cell") c.cell = parse_int(need(i, "--cell"), "cell");
    else if (arg == "--calib") c.calib_files.push_back(need(i, "--calib"));
    else if (arg == "--avmip") c.avmips.push_back(parse_double(need(i, "--avmip"), "avmip"));
    else if (arg == "--ped-sigma") c.ped_sigma = parse_double(need(i, "--ped-sigma"), "ped-sigma");
    else if (arg == "--layers") c.layers_in_segment = parse_int(need(i, "--layers"), "layers");
    else if (arg == "--vov") c.vov = parse_double(need(i, "--vov"), "vov");
    else if (arg == "--fit-option") c.fit_option = need(i, "--fit-option");
    else if (arg == "--repeat") c.repeat = parse_int(need(i, "--repeat"), "repeat");
    else if (arg == "--fit-low") c.fit_low = parse_double(need(i, "--fit-low"), "fit-low");
    else if (arg == "--fit-high") c.fit_high = parse_double(need(i, "--fit-high"), "fit-high");
    else if (arg == "--start-mp") c.start_mp = parse_double(need(i, "--start-mp"), "start-mp");
    else if (arg == "--mp-low") c.mp_low = parse_double(need(i, "--mp-low"), "mp-low");
    else if (arg == "--mp-high") c.mp_high = parse_double(need(i, "--mp-high"), "mp-high");
    else if (arg == "--scan") {
      c.scan_start = parse_double(need(i, "--scan"), "scan start");
      c.scan_stop = parse_double(need(i, "--scan"), "scan stop");
      c.scan_step = parse_double(need(i, "--scan"), "scan step");
    } else {
      throw std::runtime_error("unknown option: " + arg);
    }
  }

  if (c.repeat < 1) throw std::runtime_error("--repeat must be >= 1");
  if (c.layers_in_segment < 1) throw std::runtime_error("--layers must be >= 1");
  if (c.scan_step && *c.scan_step <= 0) throw std::runtime_error("scan step must be > 0");
  return c;
}

Seed seed_from_calib(const std::string &path, int cell, bool override_ped,
                     double ped_override) {
  std::ifstream in(path);
  if (!in) throw std::runtime_error("cannot open calibration: " + path);

  double sum = 0.0;
  int active = 0;
  bool found_cell = false;
  double cell_ped_sigma = std::numeric_limits<double>::quiet_NaN();

  std::string line;
  while (std::getline(in, line)) {
    if (line.empty() || line[0] == '#') continue;
    std::istringstream ss(line);
    std::vector<double> v;
    double x = 0.0;
    while (ss >> x) v.push_back(x);
    if (v.size() != 18) continue;

    const int id = static_cast<int>(v[0]);
    const double scale_h = v[9];
    const int bad_channel = static_cast<int>(v[17]);

    if (id == cell) {
      found_cell = true;
      cell_ped_sigma = v[6];
    }

    if (scale_h != -1000.0 && bad_channel >= 2) {
      sum += scale_h;
      ++active;
    }
  }

  if (!found_cell) {
    throw std::runtime_error("cell " + std::to_string(cell) +
                             " not found in calibration: " + path);
  }
  if (active == 0) throw std::runtime_error("no active MIP scales in calibration: " + path);

  Seed s;
  s.label = path;
  s.avmip = sum / active;
  s.ped_sigma = override_ped ? ped_override : cell_ped_sigma;
  s.active_channels = active;
  return s;
}

double minimum_x_in_range(const TH1 &h, double min_x, double max_x) {
  double min_y = 1e6;
  double x_value = -10000.0;
  const int first = h.FindBin(min_x);
  const int last = h.FindBin(max_x);
  for (int i = first; i < last + 1; ++i) {
    if (min_y > h.GetBinContent(i)) {
      min_y = h.GetBinContent(i);
      x_value = h.GetBinCenter(i);
    }
  }
  return x_value;
}

struct FitSetup {
  double min_x = 0.0;
  double fit_low = 0.0;
  double fit_high = 0.0;
  double int_area = 0.0;
  double start[4]{};
  double low[4]{};
  double high[4]{};
};

FitSetup production_setup(const TH1 &h, const Config &c, const Seed &seed) {
  FitSetup s;
  const double avmip = seed.avmip;
  const double ped = seed.ped_sigma;

  if (c.layers_in_segment == 1) {
    s.fit_low = 0.6 * avmip;
    s.fit_high = 3.0 * avmip;
  } else if (c.layers_in_segment < 6) {
    s.fit_low = 0.3 * avmip;
    s.fit_high = 3.0 * avmip;
  } else {
    s.fit_low = 0.6 * avmip;
    s.fit_high = 4.0 * avmip;
  }
  if (c.vov > 6.0) s.fit_high *= 1.2;

  s.min_x = minimum_x_in_range(h, 0.0, 0.8 * avmip);
  if (s.fit_low > s.min_x) s.fit_low = s.min_x;

  if (c.fit_low) s.fit_low = *c.fit_low;
  if (c.fit_high) s.fit_high = *c.fit_high;

  s.int_area = h.Integral(h.FindBin(s.fit_low), h.FindBin(s.fit_high));

  s.start[0] = ped * 3.0;
  s.low[0] = 0.1;
  s.high[0] = 100.0;
  if (c.vov > 6.0) s.high[0] = 150.0;
  if (c.vov < 4.5) s.low[0] *= 0.1;

  s.start[1] = avmip;
  if (c.layers_in_segment == 1) {
    s.low[1] = 0.5 * avmip;
    s.high[1] = 1.7 * avmip;
  } else if (c.layers_in_segment < 6) {
    s.low[1] = 0.3 * avmip;
    s.high[1] = 2.2 * avmip;
  } else {
    s.low[1] = 0.5 * avmip;
    s.high[1] = 3.5 * avmip;
  }
  if (s.low[1] > s.min_x) s.low[1] = s.min_x;
  if (c.vov > 6.0) s.high[1] *= 1.2;

  s.start[2] = s.int_area;
  s.low[2] = 1.0;
  s.high[2] = s.int_area * 5.0;

  s.start[3] = ped;
  s.low[3] = ped * 0.01;
  s.high[3] = ped * 30.0;
  if (c.layers_in_segment > 5) s.high[3] = ped * 50.0;
  if (c.vov > 6.0) s.high[3] *= 2.0;
  if (c.vov < 4.0) s.low[3] *= 0.1;

  if (c.start_mp) s.start[1] = *c.start_mp;
  if (c.mp_low) s.low[1] = *c.mp_low;
  if (c.mp_high) s.high[1] = *c.mp_high;

  return s;
}

void print_header() {
  std::cout
      << "seed,avmip,ped_sigma,active_channels,repeat,fit_option,fit_status,valid,"
      << "langau_status,min_x,fit_low,fit_high,int_area,"
      << "start_width,start_mp,start_area,start_gsigma,"
      << "width,width_err,mp,mp_err,area,area_err,gsigma,gsigma_err,"
      << "peak,fwhm,chi2,ndf,"
      << "width_low,width_high,mp_low,mp_high,area_low,area_high,gsigma_low,gsigma_high\n";
}

void print_csv_string(const std::string &text) {
  std::cout << '"';
  for (char c : text) {
    if (c == '"') std::cout << '"';
    std::cout << c;
  }
  std::cout << '"';
}

void run_fit(const TH1 &source, const Config &c, const Seed &seed, int repeat) {
  std::unique_ptr<TH1> hist(dynamic_cast<TH1 *>(
      source.Clone(("cell_fit_" + std::to_string(repeat)).c_str())));
  if (!hist) throw std::runtime_error("failed to clone histogram");
  hist->SetDirectory(nullptr);

  FitSetup setup = production_setup(*hist, c, seed);

  ROOT::Math::MinimizerOptions::SetDefaultMinimizer("Minuit2", "Migrad");
  ROOT::Math::MinimizerOptions::SetDefaultMaxFunctionCalls(1000);
  ROOT::Math::MinimizerOptions::SetDefaultMaxIterations(100);

  TF1 signal(("fmip_cell_" + std::to_string(repeat)).c_str(),
             langaufun, setup.fit_low, setup.fit_high, 4);
  signal.SetNpx(1000);
  signal.SetParameters(setup.start);
  signal.SetParNames("Width", "MP", "Area", "GSigma");
  for (int i = 0; i < 4; ++i) signal.SetParLimits(i, setup.low[i], setup.high[i]);

  int fit_status = hist->Fit(&signal, c.fit_option.c_str());
  int valid = signal.IsValid() ? 1 : 0;

  double p[4];
  signal.GetParameters(p);
  double peak = std::numeric_limits<double>::quiet_NaN();
  double fwhm = std::numeric_limits<double>::quiet_NaN();
  int langau_status = langaupro(p, peak, fwhm);

  print_csv_string(seed.label);
  std::cout << std::setprecision(15)
            << ',' << seed.avmip
            << ',' << seed.ped_sigma
            << ',' << seed.active_channels
            << ',' << repeat
            << ',';
  print_csv_string(c.fit_option);
  std::cout
      << ',' << fit_status
      << ',' << valid
      << ',' << langau_status
      << ',' << setup.min_x
      << ',' << setup.fit_low
      << ',' << setup.fit_high
      << ',' << setup.int_area
      << ',' << setup.start[0]
      << ',' << setup.start[1]
      << ',' << setup.start[2]
      << ',' << setup.start[3]
      << ',' << signal.GetParameter(0)
      << ',' << signal.GetParError(0)
      << ',' << signal.GetParameter(1)
      << ',' << signal.GetParError(1)
      << ',' << signal.GetParameter(2)
      << ',' << signal.GetParError(2)
      << ',' << signal.GetParameter(3)
      << ',' << signal.GetParError(3)
      << ',' << peak
      << ',' << fwhm
      << ',' << signal.GetChisquare()
      << ',' << signal.GetNDF()
      << ',' << setup.low[0]
      << ',' << setup.high[0]
      << ',' << setup.low[1]
      << ',' << setup.high[1]
      << ',' << setup.low[2]
      << ',' << setup.high[2]
      << ',' << setup.low[3]
      << ',' << setup.high[3]
      << '\n';
}

}  // namespace

int main(int argc, char **argv) {
  try {
    Config c = parse_args(argc, argv);

    TFile input(c.input.c_str(), "READ");
    if (input.IsZombie()) throw std::runtime_error("cannot open ROOT file: " + c.input);

    TH1 *source = nullptr;
    std::string used_path;
    if (!c.hist_path.empty()) {
      source = dynamic_cast<TH1 *>(input.Get(c.hist_path.c_str()));
      used_path = c.hist_path;
    } else {
      const std::vector<std::string> candidates = {
          "cell903",
          "IndividualCellsTrigg/hspectramipTriggADCCellID" + std::to_string(c.cell)};
      for (const auto &path : candidates) {
        source = dynamic_cast<TH1 *>(input.Get(path.c_str()));
        if (source) {
          used_path = path;
          break;
        }
      }
    }
    if (!source) throw std::runtime_error("target histogram not found");

    std::cerr << "histogram=" << used_path
              << " entries=" << source->GetEntries()
              << " bins=" << source->GetNbinsX() << '\n';

    std::vector<Seed> seeds;
    for (const auto &path : c.calib_files) {
      seeds.push_back(seed_from_calib(
          path, c.cell, c.ped_sigma.has_value(),
          c.ped_sigma.value_or(0.581290)));
    }

    const double manual_ped = c.ped_sigma.value_or(0.581290);
    for (double avmip : c.avmips) {
      seeds.push_back({"avmip=" + std::to_string(avmip), avmip, manual_ped, -1});
    }

    if (c.scan_start && c.scan_stop && c.scan_step) {
      const double eps = *c.scan_step * 1e-9;
      for (double x = *c.scan_start; x <= *c.scan_stop + eps; x += *c.scan_step) {
        std::ostringstream label;
        label << "scan=" << std::setprecision(15) << x;
        seeds.push_back({label.str(), x, manual_ped, -1});
      }
    }

    if (seeds.empty()) {
      seeds.push_back({"refine2-range-seed", 52.10410788425, manual_ped, -1});
      seeds.push_back({"refine3-range-seed", 52.09756765275, manual_ped, -1});
    }

    print_header();
    for (const auto &seed : seeds) {
      for (int r = 1; r <= c.repeat; ++r) run_fit(*source, c, seed, r);
    }
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "fit_cell903: " << e.what() << '\n';
    return 1;
  }
}
