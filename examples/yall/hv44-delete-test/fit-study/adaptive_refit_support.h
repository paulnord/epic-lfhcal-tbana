#ifndef LFHCAL_ADAPTIVE_REFIT_SUPPORT_H
#define LFHCAL_ADAPTIVE_REFIT_SUPPORT_H
// Reuse, do not fork, the numerical implementation validated by
// check_fixed_widths.C. This file adds post-fit checks, not fitting rules.
#include "fixed_width_numerics.h"
#include <string>

namespace adaptive_refit {
inline double missing() { return std::numeric_limits<double>::quiet_NaN(); }
struct Check {
  fixed_width::WidthResult curve{missing(),missing(),missing(),missing(),missing(),missing(),missing()};
  double peak_change=missing(), width_change=missing(), curve_change=missing();
  double fit_bins_change=missing(), span8_peak_change=missing(), span8_width_change=missing();
  double span8_curve_change=missing(), error_estimate=missing();
  int max_evaluations=0;
  bool complete=false, pass=false;
  std::string error;
};

inline Check verify(fixed_width::Parameters p, fixed_width::Function pdf,
                    double rtol, const std::vector<double> &bin_centres) {
  Check result;
  try {
    using namespace fixed_width;
    Convolution loose(p,pdf,rtol,5), tight(p,pdf,rtol*0.01,5), wide(p,pdf,rtol*0.01,8);
    const double scale=std::max(p.width,p.sigma);
    const auto ml=measure(std::ref(loose),p.mp,scale);
    const auto mt=measure(std::ref(tight),p.mp,scale);
    const auto mw=measure(std::ref(wide),p.mp,scale);
    result.curve=mt;
    result.peak_change=mt.peak-ml.peak;
    result.width_change=mt.fwhm-ml.fwhm;
    result.span8_peak_change=mw.peak-mt.peak;
    result.span8_width_change=mw.fwhm-mt.fwhm;
    result.curve_change=0;
    result.fit_bins_change=0;
    result.span8_curve_change=0;
    std::vector<double> grid{mt.left,mt.peak,mt.right,p.mp,p.mp+1};
    for(int k=0;k<=128;++k) grid.push_back(p.mp+scale*(-4.+12.*k/128.));
    for(double x:grid) {
      const double ft=tight(x);
      result.curve_change=std::max(result.curve_change,std::abs(loose(x)-ft)/mt.height);
      result.span8_curve_change=std::max(result.span8_curve_change,std::abs(wide(x)-ft)/mt.height);
    }
    for(double x:bin_centres)
      result.fit_bins_change=std::max(result.fit_bins_change,std::abs(loose(x)-tight(x))/mt.height);
    result.error_estimate=tight.max_estimated_error();
    result.max_evaluations=tight.max_calls();
    result.pass=std::abs(result.peak_change)<1e-3 && std::abs(result.width_change)<1e-4 &&
                result.curve_change<1e-7 && result.fit_bins_change<1e-7;
    result.complete=true;
    if(!result.pass) result.error="tighter-integration stability thresholds not met";
  } catch(const std::exception &e) {
    result.error=e.what();
  }
  return result;
}
} // namespace adaptive_refit
#endif
