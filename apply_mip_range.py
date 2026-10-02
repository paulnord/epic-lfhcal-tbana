#!/usr/bin/env python3
"""Apply the same range-only change to either archived production fitter."""
import hashlib
from pathlib import Path
EXPECTED={'249fd7785c71297f76925d1a367b63b41ff6889db261ccc2e82d3323dce3b20a','b0dcde82cc5f139519777acb4ba9fab2c241b553aee49c3b5c1b7554c9520a25'}
ANCHOR='  GetFitRange(fitrange, year, true,  impE, vov, avmip);'
INSERT=r'''
  // Frozen valley rule: refinement only; original bins and fitter untouched.
  if (ROType == ReadOut::Type::Hgcroc && impE) {
    std::vector<double> rangeX, rangeY;
    for (int b=1; b<=hspectraHG.GetNbinsX(); ++b) {
      rangeX.push_back(hspectraHG.GetBinCenter(b));
      rangeY.push_back(hspectraHG.GetBinContent(b));
    }
    const double oldLower=fitrange[0];
    const auto boundary=lfhcal::mip_range_v1::choose(
        rangeX,rangeY,calib->PedestalSigH,avmip,oldLower);
    fitrange[0]=boundary.lower;
    const auto oldPrecision=std::cout.precision();
    std::cout << std::setprecision(17) << "LFHCAL_RANGE_V1 cell=" << cellID
              << " sample=" << TileName.Data() << " status=" << boundary.reason
              << " usable=" << boundary.usable << " old=" << oldLower
              << " new=" << boundary.lower << " peak=" << boundary.observed
              << " valley=" << boundary.valley << " fraction=" << boundary.fraction
              << std::endl;
    std::cout.precision(oldPrecision);
  }
'''
def transform(source):
 if hashlib.sha256(source.encode()).hexdigest() not in EXPECTED:raise ValueError('Unreviewed TileSpectra.cc; refusing patch')
 if source.count(ANCHOR)!=1:raise ValueError('Range anchor mismatch')
 return source.replace('#include "TileSpectra.h"','#include "TileSpectra.h"\n#include "MipRangeFinder.h"\n#include <iomanip>',1).replace(ANCHOR,ANCHOR+INSERT,1)
def apply(root,header):
 p=Path(root)/'NewStructure/TileSpectra.cc';p.write_text(transform(p.read_text()));(p.parent/'MipRangeFinder.h').write_bytes(Path(header).read_bytes())
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--header',type=Path,required=True);a=p.parse_args();apply(a.source,a.header)
