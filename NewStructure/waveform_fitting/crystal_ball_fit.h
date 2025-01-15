// Fit the waveform with a crystal ball function

#pragma once

#include "waveform_fit_base.h"

#include <vector>

#include <TF1.h>
#include <TGraph.h>

class crystal_ball_fit : public waveform_fit_base {
public:
    crystal_ball_fit();
    ~crystal_ball_fit();
    
    void fit() override;

private:
    double crystal_ball(double *inputs, double *parameters);

    TF1 *crystal_ball_function;
    TGraph *crystal_ball_graph;

};