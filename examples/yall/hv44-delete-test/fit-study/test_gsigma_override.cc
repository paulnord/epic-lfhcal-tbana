// Exercise the actual parser and fit-setup functions without running a fit.
// Including the implementation in this test translation unit avoids copying
// the setup rules into a second implementation.
#define main cell903_application_main
#include "fit_cell903.cc"
#undef main
#include "TH1D.h"
#include <initializer_list>

namespace {
void expect(bool ok, const char *message) {
  if (!ok) throw std::runtime_error(message);
}
Config args(std::initializer_list<std::string> options) {
  std::vector<std::string> text{"fit_cell903", "unused.root"};
  text.insert(text.end(), options.begin(), options.end());
  std::vector<char *> argv;
  for (auto &s : text) argv.push_back(s.data());
  return parse_args(static_cast<int>(argv.size()), argv.data());
}
template<class F> void must_throw(F f) {
  bool caught=false;
  try {f();} catch (const std::runtime_error &) {caught=true;}
  expect(caught,"expected invalid Gaussian bound to be rejected");
}
void same_except_sigma_high(const FitSetup &a, const FitSetup &b, double cap) {
  expect(a.min_x==b.min_x && a.fit_low==b.fit_low &&
         a.fit_high==b.fit_high && a.int_area==b.int_area,
         "Gaussian bound override changed histogram/fit-range setup");
  for (int i=0;i<4;++i) {
    expect(a.start[i]==b.start[i],"override changed a starting value");
    expect(a.low[i]==b.low[i],"override changed a lower bound");
    if (i!=3) expect(a.high[i]==b.high[i],"override changed another upper bound");
  }
  expect(b.high[3]==cap,"Gaussian upper bound was not applied");
}
}

int main() {
  try {
    TH1D h("sigma_override_test","",1124,-100,1024);
    h.SetDirectory(nullptr);
    for(int i=0;i<92;++i) h.Fill(70.0+(i%10));
    const Seed seed{"test",52.1041078842105,0.581290,190};
    const Config defaults=args({});
    expect(!defaults.gsigma_high,"override unexpectedly enabled by default");
    const auto baseline=production_setup(h,defaults,seed);
    expect(std::abs(baseline.high[3]-29.0645)<1e-12,"default cap changed");
    const auto extended=args({"--gsigma-high","58.129"});
    same_except_sigma_high(baseline,production_setup(h,extended,seed),58.129);

    // Also preserve starts and other limits across each setup-rule branch.
    for(int layers : {1,5,8}) for(double vov : {3.5,5.7,7.0}) {
      Config a=defaults;
      a.layers_in_segment=layers;
      a.vov=vov;
      Config b=a;
      b.gsigma_high=120.0;
      same_except_sigma_high(production_setup(h,a,seed),production_setup(h,b,seed),120.0);
    }
    for (const std::string value : {"nan","inf","-1","0","bad","58.129x"})
      must_throw([&]{args({"--gsigma-high",value});});
    must_throw([&]{args({"--gsigma-high"});});
    for (double cap : {baseline.low[3]/2, baseline.low[3], 0.1, seed.ped_sigma}) {
      Config c=defaults;
      c.gsigma_high=cap;
      must_throw([&]{production_setup(h,c,seed);});
    }
    std::cout<<"PASS: Gaussian-sigma override changes only high[3]; defaults and invalid-input checks passed.\n";
    return 0;
  } catch(const std::exception &e) {
    std::cerr<<"test_gsigma_override: "<<e.what()<<'\n';
    return 1;
  }
}
