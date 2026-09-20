#include "LangauNumerics.h"
#include <iostream>
#include <string>

namespace {
using namespace lfhcal::langau;

void expect_failure(const std::function<void()> &action, const std::string &message) {
  try {
    action();
  } catch (const std::runtime_error &error) {
    require(std::string(error.what()).find(message) != std::string::npos,
            "operation failed for an unexpected reason");
    return;
  }
  throw std::runtime_error("expected failure was not reported: " + message);
}

void analytic_controls() {
  const double pi=std::acos(-1.0);
  for(double sigma : {0.05,1.0,29.0645,100.0}) {
    const double centre=70.0;
    Function g=[=](double x){return std::exp(-0.5*std::pow((x-centre)/sigma,2));};
    auto m=measure(g,centre,sigma);
    const double expected=2*std::sqrt(2*std::log(2.0))*sigma;
    require(std::abs(m.fwhm-expected)<1e-7*std::max(1.,sigma),"Gaussian FWHM control failed");
  }
  // Analytic Gaussian-Gaussian convolution with exactly the same finite
  // t=x +/-5 sigma interval. Covers broad/narrow scale ratios in either direction.
  Function normal=[=](double u){return std::exp(-u*u/2)/std::sqrt(2*pi);};
  for(double width : {0.1,0.5,29.0645,100.0}) {
    Parameters p{width,70.,93.,29.0645};
    Convolution conv(p,normal,1e-10,5);
    const double mean=p.mp+.22278298*p.width;
    const double total=std::hypot(p.width,p.sigma);
    for(double k : {-3.,-1.,0.,1.,3.}) {
      const double x=mean+k*total;
      const double cm=(p.sigma*p.sigma*mean+p.width*p.width*x)/(total*total);
      const double cs=p.width*p.sigma/total;
      const double mass=.5*(std::erf((x+5*p.sigma-cm)/(std::sqrt(2.)*cs))-
                              std::erf((x-5*p.sigma-cm)/(std::sqrt(2.)*cs)));
      const double expected=p.area/(total*std::sqrt(2*pi))*std::exp(-k*k/2)*mass;
      const double got=conv(x);
      require(std::abs(got-expected)<1e-8*std::max(1e-6,expected),
              "finite-interval Gaussian convolution control failed");
    }
  }
}

void verification_controls() {
  const double pi=std::acos(-1.0);
  const Function normal=[=](double u){return std::exp(-u*u/2)/std::sqrt(2*pi);};
  for (double rtol : {1e-8,1e-10}) {
    const auto check=verify({0.1,70.,93.,29.0645},normal,rtol,{4.5,70.,73.5,207.5});
    require(check.complete && check.pass,"adaptive post-fit Gaussian control failed");
    require(check.error.empty(),"successful verification recorded an error");
    require(std::abs(check.curve.left_fraction-.5)<1e-8,"bad left half height");
    require(std::abs(check.curve.right_fraction-.5)<1e-8,"bad right half height");
    require(check.max_evaluations>0 && check.max_evaluations<=500000,
            "quadrature evaluation diagnostic missing");
    require(std::isfinite(check.error_estimate) && check.error_estimate>=0,
            "quadrature error diagnostic missing");
    require(std::isfinite(check.span8_peak_change) && std::isfinite(check.span8_width_change) &&
            std::isfinite(check.span8_curve_change),"wider-interval diagnostic missing");
  }
  const double nan=std::numeric_limits<double>::quiet_NaN();
  const double inf=std::numeric_limits<double>::infinity();
  const Parameters invalid[] = {
    {-1.,70.,93.,29.0645}, {0.,70.,93.,29.0645}, {nan,70.,93.,29.0645},
    {inf,70.,93.,29.0645}, {.1,nan,93.,29.0645}, {.1,inf,93.,29.0645},
    {.1,70.,0.,29.0645}, {.1,70.,-1.,29.0645}, {.1,70.,nan,29.0645},
    {.1,70.,inf,29.0645}, {.1,70.,93.,0.}, {.1,70.,93.,-1.},
    {.1,70.,93.,nan}, {.1,70.,93.,inf}
  };
  for (const auto &p : invalid) {
    const auto bad=verify(p,normal,1e-10,{});
    require(!bad.complete && !bad.pass && !bad.error.empty(),"invalid vector not rejected");
    require(std::isnan(bad.curve.peak) && std::isnan(bad.curve.fwhm),
            "failed measurement was converted to a usable calibration value");
  }
  for (double tolerance : {0.,-1.,1.,inf,nan}) {
    expect_failure([&] {Convolution({.1,70.,93.,29.0645},normal,tolerance);},
                   "invalid integration settings");
  }
  for (double span : {4.9,12.1,inf,nan}) {
    expect_failure([&] {Convolution({.1,70.,93.,29.0645},normal,1e-10,span);},
                   "invalid integration settings");
  }
  expect_failure([&] {Convolution({1e-15,70.,93.,29.0645},normal,1e-10)(70.);},
                 "parameter ratio exceeds diagnostic domain");
  const auto bad_pdf=verify({.1,70.,93.,29.0645},[=](double){return nan;},1e-10,{});
  require(!bad_pdf.complete && !bad_pdf.pass && std::isnan(bad_pdf.curve.fwhm) &&
          bad_pdf.error=="nonfinite or negative curve evaluation", "bad PDF was not rejected");
}

void convergence_and_bracketing_controls() {
  const Function gaussian=[](double x){return std::exp(-x*x/2);};
  const double nan=std::numeric_limits<double>::quiet_NaN();
  expect_failure([&] {measure(gaussian,0.,0.);},"invalid search scale");
  expect_failure([&] {measure(gaussian,nan,1.);},"invalid search scale");
  expect_failure([] {measure([](double){return 0.;},0.,1.);},"zero curve across peak-search window");
  expect_failure([] {measure([](double){return -1.;},0.,1.);},"nonfinite or negative curve evaluation");
  expect_failure([&] {measure([=](double){return nan;},0.,1.);},"nonfinite or negative curve evaluation");
  expect_failure([] {measure([](double x){return x+10000.;},0.,1.);},"unable to bracket the peak");
  expect_failure([] {
    measure([](double x){return std::exp(-std::pow(x-3.,2))+
                               std::exp(-std::pow(x+3.,2));},0.,1.);
  },"multiple resolved peaks");
  expect_failure([] {
    measure([](double x){return .75+.25*std::exp(-x*x/2);},0.,1.);
  },"unable to bracket half-height crossing");
  // An insufficient subdivision budget must fail instead of returning the
  // first finite quadrature estimate as a converged integral.
  expect_failure([] {
    const Function step=[](double x){return x<.2 ? 1. : 2.;};
    int calls=0;
    double error=0.;
    const double coarse=gauss16(step,0.,1.,calls);
    adaptive(step,0.,1.,coarse,1e-30,1e-30,0,calls,error);
  },"quadrature subdivision did not converge");
  expect_failure([&] {
    int calls=500000;
    gauss16(gaussian,0.,1.,calls);
  },"quadrature evaluation budget exhausted");
}
} // namespace

int main() {
  try {
    analytic_controls();
    verification_controls();
    convergence_and_bracketing_controls();
    std::cout << "PASS: 24 analytic controls, post-fit convergence, invalid vectors/settings, "
                 "failure preservation, peak/half-height bracketing and quadrature budgets.\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
