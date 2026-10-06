#include "TileSpectra.h"
#include "TError.h"
#include <cassert>
#include <iostream>
#ifdef TRACK_FIT_ARRAYS
#include <map>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <new>
static bool trackArrays=false;
static std::map<void*,std::size_t> fitArrays;
void* operator new[](std::size_t n) {
  void* ptr=std::malloc(n);
  if (!ptr) throw std::bad_alloc();
  Dl_info where{};
  if (trackArrays && dladdr(__builtin_return_address(0),&where) && where.dli_sname &&
      (std::strstr(where.dli_sname,"FitMipHG") || std::strstr(where.dli_sname,"FitMipLG")))
    fitArrays[ptr]=n;
  return ptr;
}
void operator delete[](void* ptr) noexcept { fitArrays.erase(ptr); std::free(ptr); }
void operator delete[](void* ptr,std::size_t) noexcept { fitArrays.erase(ptr); std::free(ptr); }
#endif

int main() {
  gErrorIgnoreLevel = kFatal;
  double out[16]={}, errors[16]={};
  TileCalib cal;
  cal.PedestalSigH=2.; cal.PedestalSigL=2.; cal.BadChannel=3;
  TileSpectra hg("reject",67,&cal,ReadOut::Type::Hgcroc,1,0);
  hg.GetHG()->SetBinContent(hg.GetHG()->FindBin(0.),1.e9);
  hg.GetHG()->SetBinContent(hg.GetHG()->FindBin(10.),1000.);
#ifdef TRACK_FIT_ARRAYS
  trackArrays=true;
#endif
  for (int i=0; i<1000; ++i)
    assert(!hg.FitMipHG(out,errors,0,2026,false,4.7,-1000.));
  cal.BadChannel=0;
  TileSpectra lg("reject",67,&cal,ReadOut::Type::Caen,1,0);
  for (int i=0; i<1000; ++i)
    assert(!lg.FitMipLG(out,errors,0,2026,false,4.7,-1000.));
  // Empty histogram reaches the fitter and rejects after allocating parameter buffers.
  cal.BadChannel=3;
  hg.GetHG()->Reset();
  for (int i=0; i<32; ++i)
    assert(!hg.FitMipHG(out,errors,0,2026,false,4.7,-1000.));
  std::cout << "PASS 1000 HG S/B rejects, 1000 LG dead-channel rejects, 32 empty HG fits\n";
#ifdef TRACK_FIT_ARRAYS
  trackArrays=false;
  std::size_t bytes=0;
  for (const auto& a:fitArrays) bytes+=a.second;
  std::cout << "Outstanding arrays allocated directly by FitMipHG/FitMipLG: " << fitArrays.size() << " (" << bytes << " bytes)\n";
  return bytes?2:0;
#endif
}
