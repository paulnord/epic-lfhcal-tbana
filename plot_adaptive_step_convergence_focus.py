#!/usr/bin/env python3
"""Focused B1/B2/E1/E2/E3 step convergence plot with +/-1 ADC references."""

from plot_adaptive_step_convergence import main

if __name__ == "__main__":
    main(
        default_datasets=("b1", "b2", "e1", "e2", "e3"),
        default_out="lfhcal-step-convergence-focus",
        default_lane_scale=0.14,
        default_height_per_dataset=1.5,
        default_alpha=0.18,
        default_linewidth=0.70,
    )
