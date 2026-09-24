#include "adaptive_refit_support.h"
#include <iostream>
int main() {
  try {
    fixed_width::self_test();
    const double pi=std::acos(-1.0);
    fixed_width::Function pdf=[=](double u){return std::exp(-u*u/2)/std::sqrt(2*pi);};
    for (double rtol : {1e-8,1e-10}) {
      const auto check=adaptive_refit::verify({0.1,70.,93.,29.0645},pdf,rtol,{4.5,70.,73.5,207.5});
      fixed_width::require(check.complete && check.pass,"adaptive post-fit Gaussian control failed");
      fixed_width::require(std::abs(check.curve.left_fraction-.5)<1e-8,"bad left half height");
      fixed_width::require(std::abs(check.curve.right_fraction-.5)<1e-8,"bad right half height");
    }
    const auto bad=adaptive_refit::verify({-1.,70.,93.,29.0645},pdf,1e-8,{});
    fixed_width::require(!bad.complete && !bad.pass && !bad.error.empty(),"invalid vector not rejected");
    fixed_width::require(std::isnan(bad.curve.fwhm),"failed width was converted to zero");
    std::cout<<"PASS: 24 existing controls; two post-fit tolerance controls; failure preserves NaN.\n";
    return 0;
  } catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
}
