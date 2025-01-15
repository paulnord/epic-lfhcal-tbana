#include "waveform_fit_base.h"

#include <map>
#include <vector>

waveform_fit_base::waveform_fit_base() {
    stale = true;
    E = 0;
    fit_ndf = 0;
    fit_chi2 = 0;
}

void waveform_fit_base::set_waveform(const std::vector<int> &waveform) {
    stale = true;
    this->waveform = std::vector<int>(waveform);
}

void waveform_fit_base::set_parameter(int parameter, double value) {
    stale = true;
    parameters[parameter] = value;
}

double waveform_fit_base::get_E() {
    if (stale) {
        return -1;
    }
    return E;
}

double waveform_fit_base::get_fit_ndf() {
    if (stale) {
        return -1;
    }
    return fit_ndf;
}

double waveform_fit_base::get_fit_chi2() {
    if (stale) {
        return -1;
    }
    return fit_chi2;
}