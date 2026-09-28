#ifndef LFHCAL_CONVOLUTION_BENCHMARK_MODELS_H
#define LFHCAL_CONVOLUTION_BENCHMARK_MODELS_H
#include "TF1Langau.h"
#include "../../LangauNumerics.h"
#include <TVirtualFFT.h>
#include <chrono>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

namespace lfhcal::convolution_benchmark {
// Benchmark reference only. Production code is not edited or linked.
inline double midpoint(double x, const double* p, int n) {
  const double lo=x-5*p[3], hi=x+5*p[3], step=(hi-lo)/n;
  const double mpc=p[1]+0.22278298*p[0];
  double sum=0;
  for (int i=1; i<=n/2; ++i) {
    const double left=lo+(i-.5)*step, right=hi-(i-.5)*step;
    sum += TMath::Landau(left,mpc,p[0])/p[0]*TMath::Gaus(x,left,p[3]);
    sum += TMath::Landau(right,mpc,p[0])/p[0]*TMath::Gaus(x,right,p[3]);
  }
  return p[2]*step*sum*0.3989422804014/p[3];
}
inline double adaptive(double x, const double* p, double span) {
  langau::IntegrationConfig cfg;
  cfg.gaussian_span=span;
  return langau::Convolution({p[0],p[1],p[2],p[3]},
      [](double u){return TMath::Landau(u,0.,1.);},cfg)(x);
}
inline TF1* make(const std::string& name, const std::string& method,
                 double lo, double hi, double cLo, double cHi, int n) {
  TF1* f=nullptr;
  if (method=="fft")
    f=fft_experiment::make(name,lo,hi,cLo,cHi,n);
  else if (method=="legacy100" || method=="midpoint10000") {
    const int steps=method=="legacy100" ? 100 : 10000;
    f=new TF1(name.c_str(),[steps](double*x,double*p){return midpoint(x[0],p,steps);},lo,hi,4);
  } else if (method=="adaptive5" || method=="adaptive8") {
    const double span=method=="adaptive5" ? 5. : 8.;
    f=new TF1(name.c_str(),[span](double*x,double*p){return adaptive(x[0],p,span);},lo,hi,4);
  } else throw std::invalid_argument("unknown convolution method");
  f->SetParNames("Width","MP","Area","GSigma");
  f->SetNpx(1000);
  return f;
}
inline void requireFFT(int n) {
  // TF1Convolution can silently fall back to numerical convolution without
  // FFTW. Check BOTH transform directions before accepting an FFT timing.
  std::unique_ptr<TVirtualFFT> f(TVirtualFFT::FFT(1,&n,"R2C K"));
  std::unique_ptr<TVirtualFFT> b(TVirtualFFT::FFT(1,&n,"C2R K"));
  if (!f || !b) throw std::runtime_error("FFT backend unavailable; benchmark stopped (no numerical fallback)");
}
inline std::vector<double> limits(const TF1& f) {
  std::vector<double> out;
  for (int i=0;i<4;++i) { double lo,hi; f.GetParLimits(i,lo,hi); out.push_back(lo);out.push_back(hi); }
  return out;
}
struct Sweep { double seconds=0, checksum=0; int evaluations=0; };
inline Sweep sweep(TF1& f, const std::vector<double>& x,
                   const std::vector<double>& p, int repeats, bool change) {
  Sweep out;
  f.SetParameters(p.data());
  f.Eval(x.at(0)); // warm up outside timing
  const auto begin=std::chrono::steady_clock::now();
  for (int j=0;j<repeats;++j) {
    if(change) {
      // Alternate TWO fixed vectors. Every sweep invalidates the FFT cache.
      f.SetParameter(0,p[0]*(j%2 ? 1.0001 : .9999));
    }
    for (double v:x) {out.checksum+=f.Eval(v);++out.evaluations;}
  }
  out.seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
  f.SetParameters(p.data());
  return out;
}
struct Peak {
  double peak=std::numeric_limits<double>::quiet_NaN();
  double fwhm=std::numeric_limits<double>::quiet_NaN();
  std::string error;
};
inline Peak measure(TF1& f, bool fft, double cLo, double cHi) {
  Peak out;
  try {
    const double scale=std::max(f.GetParameter(0),f.GetParameter(3));
    const double roundoff=1e-13*std::abs(f.GetParameter(2))/scale;
    const auto result=langau::measure([&](double x) {
      if(fft && (x<cLo || x>cHi))
        throw std::runtime_error("peak/FWHM search outside fixed FFT domain");
      const double y=f.Eval(x);
      // Only peak-finding ignores negative roundoff in far tails. The fitting
      // callback and saved curve evaluations are NOT clipped or altered.
      return (y<0 && y>-roundoff) ? 0. : y;
    },f.GetParameter(1),scale);
    out.peak=result.peak;out.fwhm=result.fwhm;
  } catch(const std::exception& e) {out.error=e.what();}
  return out;
}
} // namespace lfhcal::convolution_benchmark
#endif
