// ROOT-free tests of the actual numerical helper using a closed-form control.
#include "../AdaptiveLangau.h"
#include <iostream>
#include <limits>
#include <string>

using namespace lfhcal::adaptive_langau;
namespace {
int checks=0;
void check(bool ok, const char* message) {
  ++checks;
  if (!ok) throw std::runtime_error(message);
}
void close(double got, double expected, double tolerance, const char* what) {
  check(std::isfinite(got) && std::isfinite(expected)
        && std::abs(got-expected)<=tolerance, what);
}
template<class F> void rejects(F f, const char* what) {
  bool thrown=false;
  try { f(); } catch (const std::runtime_error&) { thrown=true; }
  check(thrown,what);
}
double normal(double x) {
  return std::exp(-x*x/2)/std::sqrt(2*std::acos(-1.));
}
// Exact Gaussian*Gaussian with the SAME finite x +/- span*sigma interval.
double exact(double x, Parameters p, double span=5.) {
  const double m=p.mp+.22278298*p.width;
  const double v=p.width*p.width+p.sigma*p.sigma;
  const double conditional=(m*p.sigma*p.sigma+x*p.width*p.width)/v;
  const double sd=p.width*p.sigma/std::sqrt(v);
  const double lo=(x-span*p.sigma-conditional)/(sd*std::sqrt(2.));
  const double hi=(x+span*p.sigma-conditional)/(sd*std::sqrt(2.));
  const double mass=(std::erf(hi)-std::erf(lo))/2;
  return p.area*normal((x-m)/std::sqrt(v))/std::sqrt(v)*mass;
}
}
int main() {
  try {
    const Parameters cases[] = {{3,30,1,5},{.1,30,1,10},{.01,30,1,20},
      {10,30,1,.005},{.0001,30,1,20},{100,30,10,.01}};
    for (const auto p:cases) {
      Convolution f(p,normal);
      auto cfg=IntegrationConfig{}; cfg.relative_tolerance=1e-12;
      Convolution tight(p,normal,cfg);
      const double centre=p.mp+.22278298*p.width;
      const double scale=std::hypot(p.width,p.sigma);
      const double peak=p.area/(std::sqrt(2*std::acos(-1.))*scale);
      for (int k=-20; k<=20; ++k) {
        const double x=centre+k*scale/10.;
        close(f(x),exact(x,p),peak*1e-8,"finite-span analytic convolution");
        close(f(x),tight(x),peak*1e-8,"tighter integration agreement");
      }
      auto twice=p; twice.area*=2.;
      close(Convolution(twice,normal)(centre),2*f(centre),peak*1e-12,"area normalization");
      auto shifted=p; shifted.mp+=7.;
      close(Convolution(shifted,normal)(centre+7.),f(centre),peak*1e-9,"translation");
    }
    const double mean=31.25, sigma=6.;
    const auto peak=peakWidth([&](double x){return normal((x-mean)/sigma)/sigma;},mean,sigma);
    close(peak.peak,mean,2e-6,"off-grid continuous peak");
    close(peak.fwhm,2*std::sqrt(2*std::log(2.))*sigma,2e-6,"analytic FWHM");
    close(peak.height,normal(0)/sigma,1e-12,"peak height");
    // These are actual failure tests, not a mock of the numerical kernel.
    rejects([]{Convolution({0,30,1,5},normal);},"zero Landau width rejected");
    rejects([]{Convolution({3,30,1,-5},normal);},"negative Gaussian width rejected");
    rejects([]{Convolution({3,30,1,5},normal)(std::numeric_limits<double>::quiet_NaN());},"NaN x rejected");
    rejects([]{Convolution({3,30,1,5},[](double){return -1.;})(30.);},"negative density rejected");
    rejects([]{Convolution({3,30,1,5},[](double){return std::numeric_limits<double>::quiet_NaN();})(30.);},"NaN density rejected");
    rejects([]{auto cfg=IntegrationConfig{};cfg.max_calls=16;Convolution({3,30,1,5},normal,cfg)(30.);},"budget exhaustion rejected");
    rejects([]{peakWidth([](double){return 0.;},30,5);},"empty model peak rejected");
    rejects([]{peakWidth([](double){return 1.;},30,5);},"unbracketed maximum rejected");
    std::cout << checks << " numerical checks passed (analytic controls; not ROOT/data validation).\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "FAIL after " << checks << " checks: " << e.what() << '\n';
    return 1;
  }
}
