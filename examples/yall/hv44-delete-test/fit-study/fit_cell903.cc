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

#include "adaptive_refit_support.h"
#include "TFitResult.h"
#include "TFitResultPtr.h"
#include "TNamed.h"
#include "TROOT.h"
#include "TSystem.h"
#include "TFile.h"
#include "TF1.h"
#include "TH1.h"
#include "TMath.h"
#include "Math/MinimizerOptions.h"

namespace {

// Set once per invocation, before any fits. The same resolution is used by
// the objective and the legacy peak/FWHM search. This is not a fit parameter.
int convolution_steps = 100;
bool use_adaptive = false;
double integration_rtol = 1e-8;

// The callback uses the exact same Convolution class as check_fixed_widths.C.
// A quadrature exception aborts this invocation; it is not hidden as a penalty.
double adaptive_model(double *x, double *par) {
  const fixed_width::Parameters p{par[0],par[1],par[2],par[3]};
  const fixed_width::Function pdf=[](double u){return TMath::Landau(u,0.,1.);};
  return fixed_width::Convolution(p,pdf,integration_rtol,5)(x[0]);
}

double langaufun(double *x, double *par) {
  static double invsq2pi = 0.3989422804014;
  static double mpshift = -0.22278298;
  const double np = static_cast<double>(convolution_steps);
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
  std::string csv_path;
  std::string results_root;
  std::string integrator = "fixed";
  double quad_rtol = 1e-8;
  int cell = 903;
  int layers_in_segment = 8;
  double vov = 5.7;
  std::string fit_option = "QRLMN0";
  int repeat = 1;
  int steps = 100;

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
      << "Fit the isolated cell-903 MIP histogram with a copy of the\n"
      << "LFHCal Landau-Gaussian function and improved-fit setup.\n"
      << "Reproduction of the production fits has NOT yet been established.\n\n"
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
      << "  --steps N             even convolution step count, default 100\n"
      << "  --csv FILE            write CSV separately from ROOT console messages\n"
      << "  --integrator MODE     fixed (default) or adaptive; span stays +/-5 sigma\n"
      << "  --quad-rtol X         adaptive relative tolerance, default 1e-8\n"
      << "  --results-root FILE   save full TFitResult objects and source histogram\n"
      << "  --fit-low X           override production-derived lower fit edge\n"
      << "  --fit-high X          override production-derived upper fit edge\n"
      << "  --start-mp X          override MP starting value\n"
      << "  --mp-low X            override MP lower parameter limit\n"
      << "  --mp-high X           override MP upper parameter limit\n"
      << "  -h, --help            show this help\n\n"
      << "If neither --calib, --avmip, nor --scan is supplied, two approximate\n"
      << "seeds inferred from printed refine2/refine3 TF1 ranges are used:\n"
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
  if (used != text.size() || value < std::numeric_limits<int>::min() ||
      value > std::numeric_limits<int>::max()) {
    throw std::runtime_error("invalid " + name + ": " + text);
  }
  return static_cast<int>(value);
}

Config parse_args(int argc, char **argv) {
  if (argc < 2) usage(argv[0]);
  if (std::string(argv[1]) == "-h" || std::string(argv[1]) == "--help") {
    usage(argv[0], 0);
  }

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
    else if (arg == "--csv") c.csv_path = need(i, "--csv");
    else if (arg == "--results-root") c.results_root = need(i, "--results-root");
    else if (arg == "--integrator") c.integrator = need(i, "--integrator");
    else if (arg == "--quad-rtol") c.quad_rtol = parse_double(need(i, "--quad-rtol"), "quad-rtol");
    else if (arg == "--cell") c.cell = parse_int(need(i, "--cell"), "cell");
    else if (arg == "--calib") c.calib_files.push_back(need(i, "--calib"));
    else if (arg == "--avmip") c.avmips.push_back(parse_double(need(i, "--avmip"), "avmip"));
    else if (arg == "--ped-sigma") c.ped_sigma = parse_double(need(i, "--ped-sigma"), "ped-sigma");
    else if (arg == "--layers") c.layers_in_segment = parse_int(need(i, "--layers"), "layers");
    else if (arg == "--vov") c.vov = parse_double(need(i, "--vov"), "vov");
    else if (arg == "--fit-option") c.fit_option = need(i, "--fit-option");
    else if (arg == "--repeat") c.repeat = parse_int(need(i, "--repeat"), "repeat");
    else if (arg == "--steps") c.steps = parse_int(need(i, "--steps"), "steps");
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

  if (c.integrator != "fixed" && c.integrator != "adaptive")
    throw std::runtime_error("--integrator must be fixed or adaptive");
  if (!(c.quad_rtol >= 1e-10 && c.quad_rtol <= 1e-6))
    throw std::runtime_error("--quad-rtol must be between 1e-10 and 1e-6");
  if (c.repeat < 1) throw std::runtime_error("--repeat must be >= 1");
  if (c.layers_in_segment < 1) throw std::runtime_error("--layers must be >= 1");
  if (c.steps < 2 || c.steps % 2 != 0) {
    throw std::runtime_error("--steps must be an even integer >= 2");
  }
  if (c.scan_step && (*c.scan_step <= 0 || *c.scan_stop < *c.scan_start ||
                      *c.scan_start + *c.scan_step == *c.scan_start)) {
    throw std::runtime_error("invalid scan bounds or non-advancing step");
  }
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

double minimum_x_in_range(TH1 &h, double min_x, double max_x) {
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

FitSetup production_setup(TH1 &h, const Config &c, const Seed &seed) {
  FitSetup s;
  const double avmip = seed.avmip;
  const double ped = seed.ped_sigma;

  if (!(std::isfinite(avmip) && avmip > 0 && std::isfinite(ped) && ped > 0)) {
    throw std::runtime_error("avmip and pedestal sigma must be finite and positive");
  }
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
  if (!(std::isfinite(s.fit_low) && std::isfinite(s.fit_high) &&
        s.fit_low < s.fit_high)) {
    throw std::runtime_error("invalid fit range");
  }

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

void print_header(std::ostream &csv) {
  csv
      << "seed,avmip,ped_sigma,active_channels,repeat,fit_option,fit_status,valid,"
      << "langau_status,min_x,fit_low,fit_high,int_area,"
      << "start_width,start_mp,start_area,start_gsigma,"
      << "width,width_err,mp,mp_err,area,area_err,gsigma,gsigma_err,"
      << "peak,fwhm,chi2,ndf,"
      << "width_low,width_high,mp_low,mp_high,area_low,area_high,gsigma_low,gsigma_high,"
      << "np,limits_reached,legacy_fit_gate_pass,"
      << "integrator,quad_rtol,fit_options_effective,result_present,result_valid,min_fcn,edm,n_calls,cov_status,"
      << "minimizer_type,boundary_parameters,adaptive_peak,adaptive_left,adaptive_right,adaptive_fwhm,"
      << "left_fraction,right_fraction,peak_change_tighter,fwhm_change_tighter,curve_change_tighter_over_peak,"
      << "fit_bins_change_tighter_over_peak,peak_change_span8,fwhm_change_span8,curve_change_span8_over_peak,"
      << "quad_max_error_estimate,quad_max_evaluations,numerics_complete,numerics_pass,numerics_error,"
      << "result_key,root_version,compiler,host,max_function_calls,max_iterations\n";
}

void print_csv_string(std::ostream &csv, const std::string &text) {
  csv << '"';
  for (char c : text) {
    if (c == '"') csv << '"';
    csv << c;
  }
  csv << '"';
}

void run_fit(const TH1 &source, const Config &c, const Seed &seed, int repeat,
             std::ostream &csv, TFile *results, int row_number) {
  std::unique_ptr<TH1> hist(dynamic_cast<TH1 *>(
      source.Clone(("cell_fit_" + std::to_string(repeat)).c_str())));
  if (!hist) throw std::runtime_error("failed to clone histogram");
  hist->SetDirectory(nullptr);

  FitSetup setup = production_setup(*hist, c, seed);

  ROOT::Math::MinimizerOptions::SetDefaultMinimizer("Minuit2", "Migrad");
  ROOT::Math::MinimizerOptions::SetDefaultMaxFunctionCalls(1000);
  ROOT::Math::MinimizerOptions::SetDefaultMaxIterations(100);

  TF1 signal(("fmip_cell_" + std::to_string(repeat)).c_str(),
             use_adaptive ? adaptive_model : langaufun, setup.fit_low, setup.fit_high, 4);
  signal.SetNpx(1000);
  signal.SetParameters(setup.start);
  signal.SetParNames("Width", "MP", "Area", "GSigma");
  for (int i = 0; i < 4; ++i) signal.SetParLimits(i, setup.low[i], setup.high[i]);

  // S only requests the full result. Retain Q,R,L,M,N,0 and all fit budgets.
  std::string options=c.fit_option;
  if (options.find('S')==std::string::npos && options.find('s')==std::string::npos) options += 'S';
  TFitResultPtr fit_result=hist->Fit(&signal, options.c_str());
  const int fit_status=static_cast<int>(fit_result);
  const bool has_result=fit_result.Get()!=nullptr;
  const std::string result_key="fit_result_"+std::to_string(row_number);
  if (results && has_result) {
    results->cd();
    if (fit_result->Write(result_key.c_str())<=0) throw std::runtime_error("cannot write TFitResult");
    results->Flush();
  }
  // Keep the existing CSV column for compatibility: this is TF1 validity,
  // not a claim of successful minimization or an acceptable calibration.
  int valid = signal.IsValid() ? 1 : 0;

  double p[4];
  signal.GetParameters(p);
  int limits_reached = 0;
  std::string boundaries;
  for (int i = 0; i < 4; ++i) {
    if (TMath::Abs(p[i] - setup.low[i]) < 1e-5 ||
        TMath::Abs(p[i] - setup.high[i]) < 1e-5) {
      ++limits_reached;
      if (!boundaries.empty()) boundaries += ';';
      boundaries += std::string(signal.GetParName(i))+":"+
          (TMath::Abs(p[i]-setup.low[i])<1e-5 ? "lower" : "upper");
    }
  }
  // This mirrors only the post-fit gate in FitMipHG, not its pre-fit skips.
  // Preserve the historical accepted status codes without endorsing them.
  const bool legacy_status_ok = fit_status == 0 || fit_status == 4000 ||
                                fit_status == 70 || fit_status == 4070;
  const int legacy_fit_gate_pass = valid && legacy_status_ok && limits_reached == 0;

  double peak = std::numeric_limits<double>::quiet_NaN();
  double fwhm = std::numeric_limits<double>::quiet_NaN();
  // Original columns remain legacy-only. -99 means deliberately not run.
  int langau_status = use_adaptive ? -99 : langaupro(p, peak, fwhm);
  adaptive_refit::Check check;
  if (use_adaptive) {
    std::vector<double> centres;
    for(int i=1; i<=hist->GetNbinsX(); ++i) {
      const double x=hist->GetBinCenter(i);
      if (x>=setup.fit_low && x<=setup.fit_high) centres.push_back(x);
    }
    check=adaptive_refit::verify({p[0],p[1],p[2],p[3]},
        [](double u){return TMath::Landau(u,0.,1.);}, c.quad_rtol, centres);
  }

  print_csv_string(csv, seed.label);
  csv << std::setprecision(17)
      << ',' << seed.avmip
      << ',' << seed.ped_sigma
      << ',' << seed.active_channels
      << ',' << repeat
      << ',';
  print_csv_string(csv, c.fit_option);
  csv
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
      << ',' << (use_adaptive ? 0 : c.steps)
      << ',' << limits_reached
      << ',' << legacy_fit_gate_pass << ',';
  print_csv_string(csv,c.integrator);
  csv << ',' << c.quad_rtol << ',';
  print_csv_string(csv,options);
  csv << ',' << int(has_result) << ',' << (has_result ? int(fit_result->IsValid()) : -1)
      << ',' << (has_result ? fit_result->MinFcnValue() : adaptive_refit::missing())
      << ',' << (has_result ? fit_result->Edm() : adaptive_refit::missing())
      << ',' << (has_result ? static_cast<long long>(fit_result->NCalls()) : -1)
      << ',' << (has_result ? fit_result->CovMatrixStatus() : -1) << ',';
  print_csv_string(csv,has_result ? fit_result->MinimizerType() : "");
  csv << ',';
  print_csv_string(csv,boundaries);
  csv << ',' << check.curve.peak << ',' << check.curve.left << ',' << check.curve.right
      << ',' << check.curve.fwhm << ',' << check.curve.left_fraction << ',' << check.curve.right_fraction
      << ',' << check.peak_change << ',' << check.width_change << ',' << check.curve_change
      << ',' << check.fit_bins_change << ',' << check.span8_peak_change << ',' << check.span8_width_change
      << ',' << check.span8_curve_change << ',' << check.error_estimate << ',' << check.max_evaluations
      << ',' << int(check.complete) << ',' << int(check.pass) << ',';
  print_csv_string(csv,check.error);
  csv << ',';
  print_csv_string(csv,results && has_result ? result_key : "");
  csv << ','; print_csv_string(csv,gROOT->GetVersion());
  csv << ','; print_csv_string(csv,__VERSION__);
  csv << ','; print_csv_string(csv,gSystem->HostName());
  csv << ",1000,100\n";
  csv.flush();
  if (!csv) throw std::runtime_error("failed to write CSV results");
}

}  // namespace

int main(int argc, char **argv) {
  try {
    Config c = parse_args(argc, argv);
    convolution_steps = c.steps;
    use_adaptive = c.integrator == "adaptive";
    integration_rtol = c.quad_rtol;

    TFile input(c.input.c_str(), "READ");
    if (input.IsZombie()) throw std::runtime_error("cannot open ROOT file: " + c.input);

    TH1 *source = nullptr;
    std::string used_path;
    if (!c.hist_path.empty()) {
      source = dynamic_cast<TH1 *>(input.Get(c.hist_path.c_str()));
      used_path = c.hist_path;
    } else {
      const std::vector<std::string> candidates = {
          "cell" + std::to_string(c.cell),
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
    if (source->GetDimension() != 1) throw std::runtime_error("expected a 1D histogram");

    std::cerr << "histogram=" << used_path
              << " entries=" << source->GetEntries()
              << " bins=" << source->GetNbinsX()
              << " integrator=" << c.integrator
              << " convolution_steps=" << (use_adaptive ? 0 : c.steps)
              << " quad_rtol=" << c.quad_rtol
              << " ROOT=" << gROOT->GetVersion() << " compiler=" << __VERSION__ << '\n';

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
        label << "scan=" << std::setprecision(17) << x;
        seeds.push_back({label.str(), x, manual_ped, -1});
      }
    }

    if (seeds.empty()) {
      seeds.push_back({"refine2-range-seed", 52.10410788425, manual_ped, -1});
      seeds.push_back({"refine3-range-seed", 52.09756765275, manual_ped, -1});
    }

    // Refuse existing output paths before opening either output.
    for (const auto &path : {c.csv_path,c.results_root})
      if (!path.empty() && !gSystem->AccessPathName(path.c_str()))
        throw std::runtime_error("output already exists: "+path);
    if (!c.csv_path.empty() && c.csv_path==c.results_root)
      throw std::runtime_error("CSV and ROOT outputs must be different paths");
    std::unique_ptr<TFile> results;
    if (!c.results_root.empty()) {
      results.reset(TFile::Open(c.results_root.c_str(),"NEW"));
      if (!results || results->IsZombie()) throw std::runtime_error("cannot create result ROOT file");
      results->cd();
      if (source->Write("source_histogram")<=0) throw std::runtime_error("cannot save source histogram");
      std::ostringstream metadata;
      metadata << "ROOT=" << gROOT->GetVersion() << "\ncompiler=" << __VERSION__
               << "\nhost=" << gSystem->HostName() << "\nspan=5\nmax_calls=1000\nmax_iterations=100\n";
      for(int i=0;i<argc;++i) metadata << "argv[" << i << "]=" << argv[i] << '\n';
      TNamed provenance("run_context",metadata.str().c_str());
      if (provenance.Write()<=0) throw std::runtime_error("cannot write run context");
    }
    std::ofstream csv_file;
    if (!c.csv_path.empty()) {
      // Refuse to clobber an existing file, including an input supplied as output.
      std::ifstream existing(c.csv_path);
      if (existing.good()) throw std::runtime_error("CSV already exists: " + c.csv_path);
      csv_file.open(c.csv_path);
      if (!csv_file) throw std::runtime_error("cannot create CSV: " + c.csv_path);
    }
    std::ostream &csv = c.csv_path.empty() ? std::cout : csv_file;
    print_header(csv);
    int row_number=0;
    for (const auto &seed : seeds) {
      for (int r = 1; r <= c.repeat; ++r)
        run_fit(*source, c, seed, r, csv, results.get(), ++row_number);
    }
    if(results) results->Close();
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "fit_cell903: " << e.what() << '\n';
    return 1;
  }
}
