#!/usr/bin/env python3
"""Focused B1/B2/E1/E2/E3 signed-log LFHCal convergence plot."""

from plot_adaptive_signed_residuals import main

if __name__ == "__main__":
    main(
        default_datasets=("b1", "b2", "e1", "e2", "e3"),
        default_out="lfhcal-signed-residual-focus",
        default_lane_scale=0.14,
        default_height_per_dataset=1.5,
    )
