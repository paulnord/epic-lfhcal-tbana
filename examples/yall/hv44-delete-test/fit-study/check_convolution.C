// Fixed-parameter numerical-resolution check. No histogram and no fitting.
// Parameters below are from the reported run-194 cell-903 TF1/CSV results.
// The convolution and legacy peak/FWHM search follow NewStructure/TileSpectra.cc
// at 476521685c4f2151ad40230447b15af357b9544c. Only np is varied.
// Run in the same EIC environment as the calibration:
//     root -l -b -q check_convolution.C
// This diagnoses quadrature/peak-search behavior, not fit reproducibility.

#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include "TMath.h"

namespace cell903_resolution {
using Parameters = std::array<double, 4>;

double convolution(double x, const Parameters &par, int np) {
  const double invsq2pi = 0.3989422804014;
  const double mpshift = -0.22278298;
  const double sc = 5.0;
  const double mpc = par[1] - mpshift * par[0];
  const double xlow = x - sc * par[3];
  const double xupp = x + sc * par[3];
  const double step = (xupp - xlow) / np;
  double sum = 0.0;
  for (double i = 1.0; i <= np / 2.0; ++i) {
    double xx = xlow + (i - .5) * step;
    double fland = TMath::Landau(xx, mpc, par[0]) / par[0];
    sum += fland * TMath::Gaus(x, xx, par[3]);
    xx = xupp - (i - .5) * step;
    fland = TMath::Landau(xx, mpc, par[0]) / par[0];
    sum += fland * TMath::Gaus(x, xx, par[3]);
  }
  return par[2] * step * sum * invsq2pi / par[3];
}

// Intentionally preserve the existing algorithm, including exact equality
// stopping, so quadrature resolution is the only experimental change.
int legacy_peak_width(const Parameters &params, int np,
                      double &maxx, double &fwhm) {
  double p, x = 0.0, fy, fxr, fxl, step, l, lold;
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
    l = convolution(x, params, np);
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
    l = TMath::Abs(convolution(x, params, np) - fy);
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
    l = TMath::Abs(convolution(x, params, np) - fy);
    if (l > lold) step = -step / 10;
    p += step;
  }
  if (i == maxcalls) return -3;
  fxl = x;
  fwhm = fxr - fxl;
  return 0;
}
} // namespace cell903_resolution

void check_convolution() {
  using namespace cell903_resolution;
  const char *labels[] = {"production_refine2", "production_refine3", "standalone_seed1"};
  const Parameters sets[] = {
      {0.577071700482, 70.3054415702, 93.0761931769, 27.8343526699},
      {0.417184786495, 67.2789542084, 93.0926886478, 27.0704954175},
      {0.960965111603323, 68.0772011060899, 93.7149005840848, 29.0644999995773}};

  std::cout << "Fixed parameters, no histogram, no minimizer.\n"
            << "Convolution interval remains +/-5 Gaussian sigmas.\n"
            << "The np=100 peak/FWHM is a LEGACY numerical result, not a reference truth.\n";
  std::cout << std::setprecision(12);
  for (int k = 0; k < 3; ++k) {
    const auto &p = sets[k];
    std::cout << '\n' << labels[k] << " Width=" << p[0]
              << " MP=" << p[1] << " Area=" << p[2] << " GSigma=" << p[3] << '\n';
    std::cout << "np,step,legacy_status,legacy_peak,legacy_fwhm,f_at_MP,f_at_MP_plus_1\n";
    for (int np : {100, 1000, 10000}) {
      double peak = std::numeric_limits<double>::quiet_NaN();
      double width = std::numeric_limits<double>::quiet_NaN();
      const int status = legacy_peak_width(p, np, peak, width);
      std::cout << np << ',' << 10.0 * p[3] / np << ',' << status << ','
                << peak << ',' << width << ','
                << convolution(p[1], p, np) << ','
                << convolution(p[1] + 1.0, p, np) << '\n';
    }
  }
  std::cout << "\nDenser quadrature does not refit these parameters or establish a corrected calibration.\n";
}
