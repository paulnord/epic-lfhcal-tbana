// Compile against the selected libLFHCAL; pass "adaptive" or "legacy".
// Synthetic wiring/failure checks, not a beam-data regression.
#include "../../AdaptiveLangau.h"
#include "../../TileSpectra.h"
#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace lfhcal::adaptive_langau;
void require_test(bool ok, const char* why) {
  if (!ok) throw std::runtime_error(why);
}
double pdf(double u) { return TMath::Landau(u,0.,1.); }
void fit_case(bool adaptive, ReadOut::Type type, bool improved, bool lowGain=false) {
  TileCalib cal;
  cal.PedestalSigH = type == ReadOut::Type::Hgcroc ? 5. : 10.;
  cal.PedestalSigL = 2.;
  cal.BadChannel = 3;
  TileSpectra spectra("synthetic",0,&cal,type);
  const Parameters truth = lowGain ? Parameters{3.,30.,100000.,2.}
      : type == ReadOut::Type::Hgcroc
      ? Parameters{3.,30.,100000.,5.} : Parameters{30.,300.,100000.,10.};
  Convolution reference(truth,pdf);
  auto* h = lowGain ? spectra.GetLG() : spectra.GetHG();
  const bool pedestal = improved && type==ReadOut::Type::Caen;
  for (int bin=1; bin<=h->GetNbinsX(); ++bin) {
    const double value=reference(h->GetBinCenter(bin))
        + (pedestal ? 50000.*TMath::Gaus(h->GetBinCenter(bin),0.,
            lowGain ? cal.PedestalSigL : cal.PedestalSigH,true) : 0.);
    h->SetBinContent(bin,value);
    h->SetBinError(bin,std::sqrt(value));
  }
  h->SetEntries(truth.area);
  double out[8]{}, error[8]{};
  const bool good=lowGain ? spectra.FitMipLG(out,error,0,2026,improved,5.,truth.mp)
      : spectra.FitMipHG(out,error,0,2026,improved,5.,truth.mp);
  require_test(good,"synthetic fit rejected");
  auto* fit=spectra.GetSignalModel(lowGain ? 0 : 1);
  const double peak=lowGain ? cal.ScaleL : cal.ScaleH;
  const double width=lowGain ? cal.ScaleWidthL : cal.ScaleWidthH;
  require_test(fit && std::isfinite(peak) && width>0.,
               "missing fitted model/calibration");
  double p[7]{}; fit->GetParameters(p);
  require_test(fit->GetNpar()==(pedestal ? 7 : 4),"wrong parameter count");
  const bool useAdaptive=adaptive && type==ReadOut::Type::Hgcroc;
  require_test((std::string(fit->GetTitle()).find("adaptive")!=std::string::npos)
               ==useAdaptive,"wrong evaluator label");
  for(double x : {truth.mp+.123,.123}) {
    double expected=useAdaptive ? Convolution({p[0],p[1],p[2],p[3]},pdf)(x)
        : TileSpectra::langaufun(&x,p);
    if(pedestal && p[6]>0.) expected+=p[4]*TMath::Gaus(x,p[5],p[6],true);
    require_test(std::abs(fit->Eval(x)-expected)<1e-10*std::max(1.,expected),
                 "production callback does not match selected evaluator");
  }
  std::cout << std::setprecision(17) << "fit "
            << (type==ReadOut::Type::Hgcroc ? "HGCROC" : "CAEN")
            << (lowGain ? " LG" : " HG")
            << " improved=" << improved << " peak=" << peak
            << " FWHM=" << width << '\n';
}
void failure_case() {
  TileCalib cal; cal.PedestalSigH=0.; cal.BadChannel=3;
  cal.ScaleH=123.; cal.ScaleWidthH=456.;
  TileSpectra spectra("invalid_sigma",0,&cal,ReadOut::Type::Hgcroc);
  auto* h=spectra.GetHG();
  for(int b=1;b<=h->GetNbinsX();++b) {
    const double y=1000.*std::exp(-std::pow((h->GetBinCenter(b)-35.)/10.,2));
    h->SetBinContent(b,y); h->SetBinError(b,std::sqrt(y));
  }
  h->SetEntries(10000.);
  double out[8], error[8];
  std::fill_n(out,8,987.); std::fill_n(error,8,654.);
  require_test(!spectra.FitMipHG(out,error,0,2026,false,5.,30.),
               "invalid numerical input unexpectedly succeeded");
  require_test(std::all_of(out,out+8,[](double x){return x==987.;})
      && std::all_of(error,error+8,[](double x){return x==654.;})
      && cal.ScaleH==123. && cal.ScaleWidthH==456.
      && spectra.GetSignalModel(1)==nullptr,"failed fit changed outputs/calibration");
}
int main(int argc,char** argv) {
  try {
    require_test(argc==2,"expected adaptive or legacy argument");
    const std::string mode=argv[1];
    require_test(mode=="adaptive" || mode=="legacy","unknown evaluator argument");
    const bool adaptive=mode=="adaptive";
    fit_case(adaptive,ReadOut::Type::Hgcroc,false);
    fit_case(adaptive,ReadOut::Type::Hgcroc,true);
    fit_case(adaptive,ReadOut::Type::Caen,false);
    fit_case(adaptive,ReadOut::Type::Caen,true);
    fit_case(adaptive,ReadOut::Type::Caen,false,true);
    fit_case(adaptive,ReadOut::Type::Caen,true,true);
    if(adaptive) {
      failure_case();
      fit_case(adaptive,ReadOut::Type::Hgcroc,false); // ROOT remains usable after abort.
    }
    std::cout << "Production wiring checks passed (" << mode << ").\n";
  } catch(const std::exception& e) { std::cerr << "FAILED: " << e.what() << '\n'; return 1; }
}
