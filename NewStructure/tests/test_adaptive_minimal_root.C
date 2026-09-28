// Run from the repository root:
// root -l -b -q 'NewStructure/tests/test_adaptive_minimal_root.C()'
// This checks the numerical helper and real ROOT callback semantics, not the
// full DataPrep event-selection/calibration pathway.
#include "../AdaptiveLangau.h"
#include <TF1.h>
#include <TMath.h>
#include <TROOT.h>
#include <TSystem.h>
#include <iostream>
#include <memory>

namespace minimal_root_test {
using namespace lfhcal::adaptive_langau;
int checks=0;
void check(bool ok, const char* why) {
  ++checks;
  if (!ok) throw std::runtime_error(why);
}
double pdf(double u) {return TMath::Landau(u,0.,1.);}
double callback(double* x, double* p) {
  return Convolution({p[0],p[1],p[2],p[3]},pdf)(x[0]);
}
double legacy100(double x, Parameters p) {
  const double a=x-5*p.sigma, h=10*p.sigma/100;
  double sum=0.;
  for (int i=0;i<100;++i) {
    const double t=a+(i+.5)*h;
    sum += pdf((t-p.mp-.22278298*p.width)/p.width)/p.width
           *std::exp(-.5*std::pow((x-t)/p.sigma,2));
  }
  return p.area*h*sum/(p.sigma*std::sqrt(2*std::acos(-1.)));
}
void run() {
  const Parameters cases[] = {
    {3.,30.,1.,5.}, {.1,30.,1.,10.}, {.01,30.,1.,20.},
    {10.,30.,1.,.005}, {.01,30.,1.,200.}};
  for (const auto p:cases) {
    Convolution f(p,pdf);
    auto cfg=IntegrationConfig{}; cfg.relative_tolerance=1e-12;
    Convolution tight(p,pdf,cfg);
    const double scale=std::max(p.width,p.sigma);
    const auto result=peakWidth(std::ref(f),p.mp,scale);
    check(std::isfinite(result.fwhm) && result.fwhm>0.,"finite FWHM");
    for (int k=-40;k<=120;++k) {
      const double x=p.mp+k*scale/10.;
      const double y=f(x), r=tight(x);
      check(std::isfinite(y) && y>=0. && std::abs(y-r)<1e-7*result.height,
            "Landau quadrature tolerance check");
    }
  }
  // Published smoke-run parameter vectors: expected *5-sigma* peak/FWHM.
  const Parameters known[] = {
    {1.3277387944841172,13.663296962241597,1.,2.5027438917788616},
    {2.5901327541976964,32.27195950088833,1.,4.950826449418681}};
  const double peaks[] = {14.670264346105917,34.2626608454385};
  const double widths[] = {8.776945381845831,17.26541196413669};
  for (int i=0;i<2;++i) {
    const auto p=known[i]; Convolution f(p,pdf);
    const auto r=peakWidth(std::ref(f),p.mp,std::max(p.width,p.sigma));
    check(std::abs(r.peak-peaks[i])<2e-5,"BNL reference peak regression");
    check(std::abs(r.fwhm-widths[i])<2e-5,"BNL reference FWHM regression");
  }
  const Parameters narrow{.01,30.,1.,20.}; Convolution f(narrow,pdf);
  double discrepancy=0.;
  const auto r=peakWidth(std::ref(f),narrow.mp,narrow.sigma);
  for (int k=0;k<100;++k) {
    const double x=29.+k*.037;
    discrepancy=std::max(discrepancy,std::abs(legacy100(x,narrow)-f(x))/r.height);
  }
  check(discrepancy>.01,"stress case must expose legacy-100 undersampling");
  TF1::DefaultAddToGlobalList(false);
  auto original=std::make_unique<TF1>("adaptive_test",callback,-5.,100.,4);
  original->SetParameters(3.,30.,1.,5.);
  TF1 copy(*original); // Live C++ copy, NOT the streaming Clone() operation.
  const double before=copy.Eval(30.);
  original.reset();
  copy.SetParameter(2,2.);
  const double after=copy.Eval(30.);
  check(std::isfinite(before) && before>0. && std::isfinite(after)
        && std::abs(after/before-2)<1e-12,"copied callback/area mapping");
  std::cout << checks << " ROOT numerical checks passed on ROOT "
            << gROOT->GetVersion() << ". Legacy stress discrepancy/peak="
            << discrepancy << '\n';
}
}
void test_adaptive_minimal_root() {
  try {minimal_root_test::run();}
  catch (const std::exception& e) {
    std::cerr << "FAILED: " << e.what() << '\n';
    gSystem->Exit(1);
  }
}
