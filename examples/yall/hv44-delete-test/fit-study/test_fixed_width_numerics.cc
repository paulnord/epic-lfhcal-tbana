#include "fixed_width_numerics.h"
#include <iostream>
int main() {
  try {
    fixed_width::self_test();
    std::cout << "PASS: 4 Gaussian width controls and 20 finite-interval Gaussian convolution controls\n";
    return 0;
  } catch(const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
