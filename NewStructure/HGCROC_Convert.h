// Tristan Protzman, January 2024
// Driver for converting the output of the HGCROC
// into a root file for further analysis

#include "Analyses.h"
#include "Event.h"
#include "Tile.h"
#include "HGCROC.h"

#include "waveform_fitting/waveform_fit_base.h"

#include <iostream>

int run_hgcroc_conversion(Analyses *analysis, waveform_fit_base *waveform_builder);
bool decode_position(int channel, int &x, int &y, int &z);
