#ifndef LFHCAL_ADAPTIVE_MIP_FIT_H
#define LFHCAL_ADAPTIVE_MIP_FIT_H

class TileSpectra;
namespace lfhcal { namespace adaptive {
bool fitMipHG(TileSpectra&, double*, double*, int, int, bool, double, double);
}}

#endif
