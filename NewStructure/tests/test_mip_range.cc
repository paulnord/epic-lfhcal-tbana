#include "MipRangeFinder.h"
#include <cassert>
#include <iostream>
int main(){
 std::vector<double>x,y;
 for(int b=1;b<=200;++b){double v=b-20.5;x.push_back(v);y.push_back(1000*std::exp(-.5*std::pow(v/2,2))+200*std::exp(-.5*std::pow((v-70)/9,2))+5*std::exp(-std::max(v,0.)/40));}
 const auto counts=y;
 auto r=lfhcal::mip_range_v1::choose(x,y,2.,70.,10.);
 assert(r.usable && r.lower==34.5 && r.observed==69.5);
 assert(y==counts); // Range finding must not alter fitted data.
 r=lfhcal::mip_range_v1::choose(x,y,2.,70.,40.);assert(r.usable && r.lower==40. && r.reason=="retained_original_floor");
 r=lfhcal::mip_range_v1::choose(x,y,2.,70.,90.);assert(!r.usable && r.lower==90. && r.reason=="range_excludes_peak");
 r=lfhcal::mip_range_v1::choose(x,y,2.,-1000.,10.);assert(!r.usable && r.lower==10.);
 std::fill(y.begin(),y.end(),10.);r=lfhcal::mip_range_v1::choose(x,y,2.,70.,10.);assert(!r.usable && r.reason=="no_prominent_peak");
 y[5]=std::numeric_limits<double>::quiet_NaN();r=lfhcal::mip_range_v1::choose(x,y,2.,70.,10.);assert(!r.usable && r.reason=="invalid_input");
 std::cout<<"mip_range_v1 deterministic range and preservation checks passed\n";
}
