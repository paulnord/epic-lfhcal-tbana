#ifndef LFHCAL_LANGAU_NUMERICS_H
#define LFHCAL_LANGAU_NUMERICS_H

// Adaptive Landau-Gaussian convolution and checked peak/FWHM extraction.
// The numerical algorithms and tolerances are the ones validated by the
// isolated hv44-delete-test study; this header has no ROOT dependency.
#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace lfhcal {
namespace langau {
using Function = std::function<double(double)>;
struct Parameters { double width, mp, area, sigma; };
// These are numerical/model conventions, not free fit parameters.  Keeping
// them together makes the reproducibility choices visible at the call site.
constexpr double kLandauMpvShift = 0.22278298;

struct IntegrationConfig {
  double relative_tolerance = 1e-10;
  double gaussian_span = 5.0;
  int max_calls = 500000;
  int max_depth = 18;
  double absolute_tolerance_fraction = 0.01;
  double diagnostic_gaussian_span = 8.0;
};

struct ValidationConfig {
  int peak_scan_bins = 160;
  int peak_search_expansions = 8;
  int peak_iterations = 160;
  int crossing_bracket_iterations = 64;
  int crossing_iterations = 200;
  double scan_left_scale = 8.0;
  double scan_right_scale = 12.0;
  double expansion_factor = 2.0;
  double crossing_expansion_factor = 1.8;
  double minimum_peak_fraction = 1e-5;
  double peak_tolerance = 1e-8;
  double half_height_tolerance = 1e-10;
  double crossing_tolerance_fraction = 0.01;
  double endpoint_tolerance = 1e-8;
  double curve_tolerance = 1e-7;
  double bin_tolerance = 1e-7;
  double width_tolerance = 1e-4;
  double peak_stability_tolerance = 1e-3;
  int curve_sample_points = 128;
  double curve_sample_min = -4.0;
  double curve_sample_max = 12.0;
};

// Positive abscissas and weights for the standard 16-point Gauss--Legendre
// rule on [-1, 1].  Each abscissa is evaluated at both +/-x, giving 16 calls.
inline constexpr std::array<double, 8> kGauss16Abscissas = {
  .095012509837637440185, .28160355077925891323,
  .45801677765722738634, .61787624440264374845,
  .75540440835500303390, .86563120238783174388,
  .94457502307323257608, .98940093499164993260};
inline constexpr std::array<double, 8> kGauss16Weights = {
  .18945061045506849629, .18260341504492358887,
  .16915651939500253819, .14959598881657673208,
  .12462897125553387205, .095158511682492784810,
  .062253523938647892863, .027152459411754094852};

// Breakpoints are in the dimensionless Landau coordinate u.  They resolve
// the narrow core, ROOT's approximation boundaries, and the long positive
// tail before adaptive subdivision is allowed to proceed.
inline constexpr std::array<double, 16> kLandauBreakpoints = {
  -16., -8., -5.5, -4., -2., -1., 0., 1.,
  2., 4., 5., 8., 12., 16., 50., 300.};
struct WidthResult {
  double peak, left, right, fwhm, height, left_fraction, right_fraction;
};

inline void require(bool ok, const char *message) {
  if (!ok) throw std::runtime_error(message);
}
inline double checked(const Function &f, double x) {
  const double y = f(x);
  require(std::isfinite(y) && y >= 0, "nonfinite or negative curve evaluation");
  return y;
}
// 16-point Gauss-Legendre rule. Endpoints are not sampled, which avoids
// evaluating both sides of a piecewise PDF at its approximation boundaries.
inline double gauss16(const Function &f, double a, double b, int &calls,
                       int max_calls) {
  calls += 2 * static_cast<int>(kGauss16Abscissas.size());
  require(calls <= max_calls, "quadrature evaluation budget exhausted");
  const double c = (a+b)/2, d = (b-a)/2;
  double s = 0;
  for (size_t i = 0; i < kGauss16Abscissas.size(); ++i)
    s += kGauss16Weights[i] *
         (checked(f,c-d*kGauss16Abscissas[i]) +
          checked(f,c+d*kGauss16Abscissas[i]));
  return d*s;
}
inline double adaptive(const Function &f, double a, double b, double coarse,
                       double atol, double rtol, int depth, int &calls,
                       int max_calls, double &error) {
  const double mid=(a+b)/2;
  const double l=gauss16(f,a,mid,calls,max_calls),
               r=gauss16(f,mid,b,calls,max_calls);
  const double fine=l+r, delta=std::abs(fine-coarse);
  if (delta <= atol+rtol*std::abs(fine)) { error += delta; return fine; }
  require(depth>0 && a<mid && mid<b, "quadrature subdivision did not converge");
  return adaptive(f,a,mid,l,atol/2,rtol,depth-1,calls,max_calls,error)+
         adaptive(f,mid,b,r,atol/2,rtol,depth-1,calls,max_calls,error);
}

// u=(t-mpc)/width resolves the narrow Landau on its own scale. Explicit
// breakpoints cover its core, ROOT approximation boundaries and geometric
// tails, plus the broad Gaussian. This prevents an adaptive rule from missing
// an entire narrow peak before it estimates an error.
class Convolution {
 public:
  Convolution(Parameters p, Function standard_pdf, IntegrationConfig config = {})
      : p_(p), pdf_(standard_pdf), config_(config) {
    require(std::isfinite(p.width) && p.width>0 && std::isfinite(p.sigma) && p.sigma>0 &&
            std::isfinite(p.mp) && std::isfinite(p.area) && p.area>0,
            "invalid fixed parameter vector");
    require(config_.relative_tolerance>0 && config_.relative_tolerance<1 &&
            config_.gaussian_span>=5 && config_.gaussian_span<=12 &&
            config_.max_calls>0 && config_.max_depth>0 &&
            config_.absolute_tolerance_fraction>0,
            "invalid integration settings");
  }
  double operator()(double x) const {
    const double mpc=p_.mp+kLandauMpvShift*p_.width;
    const double lo=(x-config_.gaussian_span*p_.sigma-mpc)/p_.width;
    const double hi=(x+config_.gaussian_span*p_.sigma-mpc)/p_.width;
    std::vector<double> edges{lo,hi};
    const auto add=[&](double u) { if (u>lo && u<hi) edges.push_back(u); };
    for (double u : kLandauBreakpoints) add(u);
    double extent=std::max(std::abs(lo),std::abs(hi));
    require(std::isfinite(extent) && extent<1e12, "parameter ratio exceeds diagnostic domain");
    for (double u=32; u<extent; u*=2) { add(u); add(-u); }
    for (int k=-static_cast<int>(config_.gaussian_span);
         k<=static_cast<int>(config_.gaussian_span); ++k)
      add((x+k*p_.sigma-mpc)/p_.width);
    std::sort(edges.begin(),edges.end());
    edges.erase(std::unique(edges.begin(),edges.end()),edges.end());
    Function f=[&](double u) {
      const double z=(x-mpc-p_.width*u)/p_.sigma;
      return pdf_(u)*std::exp(-0.5*z*z);
    };
    int calls=0;
    double sum=0, error=0;
    const double atol=config_.relative_tolerance *
      config_.absolute_tolerance_fraction/(edges.size()-1);
    for (size_t i=1; i<edges.size(); ++i) {
      const double a=edges[i-1], b=edges[i];
      const double coarse=gauss16(f,a,b,calls,config_.max_calls);
      sum += adaptive(f,a,b,coarse,atol,config_.relative_tolerance,
                      config_.max_depth,calls,config_.max_calls,error);
    }
    const double factor=p_.area/(p_.sigma*std::sqrt(2*std::acos(-1.0)));
    max_error_=std::max(max_error_,factor*error);
    max_calls_=std::max(max_calls_,calls);
    return factor*sum;
  }
  double max_estimated_error() const {return max_error_;}
  int max_calls() const {return max_calls_;}
 private:
  Parameters p_; Function pdf_; IntegrationConfig config_;
  mutable double max_error_=0;
  mutable int max_calls_=0;
};

// Coarse bounded survey followed by golden-section maximization. The scan
// checks for multiple resolved peaks; this is not a claim about all possible
// PDFs. A separate tighter-integration run must confirm the peak/width.
inline WidthResult measure(const Function &f, double centre, double scale,
                           const ValidationConfig &config = {}) {
  require(std::isfinite(centre) && std::isfinite(scale) && scale>0,"invalid search scale");
  const int n=config.peak_scan_bins;
  double a=centre-config.scan_left_scale*scale,
         b=centre+config.scan_right_scale*scale, lo=0, hi=0;
  bool bracketed=false;
  for (int expand=0; expand<config.peak_search_expansions; ++expand) {
    std::vector<double> y(n+1);
    int best=0;
    for (int i=0;i<=n;++i) {y[i]=checked(f,a+(b-a)*i/n); if(y[i]>y[best]) best=i;}
    require(y[best]>0,"zero curve across peak-search window");
    if (best>0 && best<n) {
      int peaks=0;
      for (int i=1;i<n;++i)
        if (y[i]>y[i-1] && y[i]>=y[i+1] && y[i]>config.minimum_peak_fraction*y[best]) ++peaks;
      require(peaks==1,"multiple resolved peaks: width is not unambiguous");
      lo=a+(b-a)*(best-1)/n; hi=a+(b-a)*(best+1)/n;
      bracketed=true; break;
    }
    a=centre+config.expansion_factor*(a-centre);
    b=centre+config.expansion_factor*(b-centre);
  }
  require(bracketed,"unable to bracket the peak");
  const double golden=(std::sqrt(5.)-1)/2;
  double l=hi-golden*(hi-lo), r=lo+golden*(hi-lo);
  double fl=checked(f,l), fr=checked(f,r);
  const double xtol=config.peak_tolerance*std::max(1.,scale);
  int iteration=0;
  for (; iteration<config.peak_iterations && hi-lo>xtol; ++iteration) {
    if (fl>fr) {hi=r; r=l; fr=fl; l=hi-golden*(hi-lo); fl=checked(f,l);}
    else {lo=l; l=r; fl=fr; r=lo+golden*(hi-lo); fr=checked(f,r);}
  }
  require(hi-lo<=xtol,"peak search did not converge");
  const double peak=(lo+hi)/2, height=checked(f,peak), half=height/2;
  require(height>0,"nonpositive peak height");
  auto crossing=[&](int direction) {
    double inside=peak, outside=peak, distance=scale;
    bool found=false;
    for(int k=0;k<config.crossing_bracket_iterations;++k) {
      outside=peak+direction*distance;
      if(checked(f,outside)<half) {found=true;break;}
      distance*=config.crossing_expansion_factor;
    }
    require(found,"unable to bracket half-height crossing");
    for(int k=0;k<config.crossing_iterations;++k) {
      const double mid=(inside+outside)/2;
      const double residual=checked(f,mid)/height-0.5;
      if(std::abs(residual)<config.half_height_tolerance) return mid;
      if(residual>0) inside=mid; else outside=mid;
      if(std::abs(inside-outside)<xtol*config.crossing_tolerance_fraction) return (inside+outside)/2;
    }
    throw std::runtime_error("half-height bisection did not converge");
  };
  const double left=crossing(-1), right=crossing(1);
  const double lf=checked(f,left)/height, rf=checked(f,right)/height;
  require(left<peak && peak<right && std::abs(lf-.5)<config.endpoint_tolerance &&
          std::abs(rf-.5)<config.endpoint_tolerance,
          "half-height residual or endpoint ordering check failed");
  return {peak,left,right,right-left,height,lf,rf};
}

inline double missing() { return std::numeric_limits<double>::quiet_NaN(); }
struct Check {
  WidthResult curve{missing(),missing(),missing(),missing(),missing(),missing(),missing()};
  double peak_change=missing(), width_change=missing(), curve_change=missing();
  double fit_bins_change=missing(), span8_peak_change=missing(), span8_width_change=missing();
  double span8_curve_change=missing(), error_estimate=missing();
  int max_evaluations=0;
  bool complete=false, pass=false;
  std::string error;
};

// The +/-8 sigma calculation is a diagnostic, not a replacement of the
// production +/-5 sigma interval and not an additional fit acceptance cut.
inline Check verify(Parameters p, Function pdf,
                    const IntegrationConfig &integration,
                    const ValidationConfig &validation,
                    const std::vector<double> &bin_centres) {
  Check result;
  try {
    IntegrationConfig tight_config = integration;
    tight_config.relative_tolerance *= integration.absolute_tolerance_fraction;
    IntegrationConfig wide_config = tight_config;
    wide_config.gaussian_span = integration.diagnostic_gaussian_span;
    Convolution loose(p,pdf,integration), tight(p,pdf,tight_config), wide(p,pdf,wide_config);
    const double scale=std::max(p.width,p.sigma);
    const auto ml=measure(std::ref(loose),p.mp,scale,validation);
    const auto mt=measure(std::ref(tight),p.mp,scale,validation);
    const auto mw=measure(std::ref(wide),p.mp,scale,validation);
    result.curve=mt;
    result.peak_change=mt.peak-ml.peak;
    result.width_change=mt.fwhm-ml.fwhm;
    result.span8_peak_change=mw.peak-mt.peak;
    result.span8_width_change=mw.fwhm-mt.fwhm;
    result.curve_change=0;
    result.fit_bins_change=0;
    result.span8_curve_change=0;
    std::vector<double> grid{mt.left,mt.peak,mt.right,p.mp,p.mp+1};
    for(int k=0;k<=validation.curve_sample_points;++k)
      grid.push_back(p.mp+scale*(validation.curve_sample_min +
                                  (validation.curve_sample_max-validation.curve_sample_min)*
                                  k/validation.curve_sample_points));
    for(double x:grid) {
      const double ft=tight(x);
      result.curve_change=std::max(result.curve_change,std::abs(loose(x)-ft)/mt.height);
      result.span8_curve_change=std::max(result.span8_curve_change,std::abs(wide(x)-ft)/mt.height);
    }
    for(double x:bin_centres)
      result.fit_bins_change=std::max(result.fit_bins_change,std::abs(loose(x)-tight(x))/mt.height);
    result.error_estimate=tight.max_estimated_error();
    result.max_evaluations=tight.max_calls();
    result.pass=std::abs(result.peak_change)<validation.peak_stability_tolerance &&
                std::abs(result.width_change)<validation.width_tolerance &&
                result.curve_change<validation.curve_tolerance &&
                result.fit_bins_change<validation.bin_tolerance;
    result.complete=true;
    if(!result.pass) result.error="tighter-integration stability thresholds not met";
  } catch(const std::exception &e) {
    result.error=e.what();
  }
  return result;
}
} // namespace langau
} // namespace lfhcal
#endif
