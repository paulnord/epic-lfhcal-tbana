// Compare the actual production legacy callback with the isolated kernel.
// Timings are single-value evaluation costs, not full calibration-chain times.
#include "../../AdaptiveLangau.h"
#include "../../TileSpectra.h"
#include <chrono>
#include <iomanip>
#include <iostream>

using namespace lfhcal::adaptive_langau;
double density(double u) { return TMath::Landau(u,0.,1.); }
// Independent uniformly spaced midpoint control; doubled resolution is checked.
double fixedGrid(double x, Parameters p, int n) {
  const double low=x-5*p.sigma, step=10*p.sigma/n;
  long double sum=0.;
  for(int i=0;i<n;++i) {
    const double t=low+(i+.5)*step;
    sum += TMath::Landau(t,p.mp+.22278298*p.width,p.width)/p.width
         *std::exp(-.5*std::pow((x-t)/p.sigma,2));
  }
  return p.area*step*sum/(p.sigma*std::sqrt(2*std::acos(-1.)));
}
template<class F> double timing(F f,double centre,double scale) {
  volatile double sink=0.;
  const auto start=std::chrono::steady_clock::now();
  constexpr int n=3000;
  for(int k=0;k<n;++k) sink+=f(centre+scale*((k%101)-50)/25.);
  const double us=std::chrono::duration<double,std::micro>(
      std::chrono::steady_clock::now()-start).count()/n;
  if(!std::isfinite(sink)) throw std::runtime_error("invalid timing sum");
  return us;
}
int main() {
  try {
    std::cout << "width,sigma,legacy_us,adaptive_us,ratio,max_grid_difference_over_peak,max_grid_refinement_over_peak\n";
    for(const auto p:{Parameters{3.,30.,1.,5.},Parameters{.1,30.,1.,10.},
                      Parameters{.01,30.,1.,20.},Parameters{10.,30.,1.,.005}}) {
      Convolution f(p,density);
      const double scale=std::max(p.width,p.sigma);
      const auto peak=peakWidth(std::ref(f),p.mp,scale);
      double difference=0.,refinement=0.;
      for(int k=-1;k<=1;++k) {
        const double x=peak.peak+k*scale;
        const double a=fixedGrid(x,p,100000),b=fixedGrid(x,p,200000);
        difference=std::max(difference,std::abs(f(x)-b)/peak.height);
        refinement=std::max(refinement,std::abs(a-b)/peak.height);
      }
      if(difference>1e-6 || refinement>1e-6)
        throw std::runtime_error("independent dense-grid control failed");
      double params[]={p.width,p.mp,p.area,p.sigma};
      const double old=timing([&](double x){return TileSpectra::langaufun(&x,params);},p.mp,scale);
      // Reconstruct each call, exactly as the production adaptive callback does.
      const double now=timing([&](double x){return Convolution(p,density)(x);},p.mp,scale);
      std::cout << std::setprecision(8) << p.width << ',' << p.sigma << ','
                << old << ',' << now << ',' << now/old << ',' << difference
                << ',' << refinement << '\n';
    }
  } catch(const std::exception& e) { std::cerr << "FAILED: " << e.what() << '\n'; return 1; }
}
