#!/usr/bin/env python3

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import ROOT


# This is the TileSpectra::langaufun implementation from
# paulnord/epic-lfhcal-tbana NewStructure/TileSpectra.cc, copied literally in
# its numerical conventions: 100 midpoint convolution samples, +/-5 Gaussian
# sigmas, CERNLIB Landau MP correction, and TMath::Gaus with its default
# unnormalized convention. The evaluator below uses the same function value
# at each histogram bin center, matching TH1::Fit option L when I is absent.
_CPP = r'''
#include "TMath.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace yawl_lfhcal_langau {

double langaufun_value(double x, double width, double mp, double area, double gsigma) {
  static double invsq2pi = 0.3989422804014;
  static double mpshift  = -0.22278298;
  static double np = 100.0;
  static double sc = 5.0;

  if (!(width > 0.0) || !(gsigma > 0.0) || !(area > 0.0)) {
    return 0.0;
  }

  double mpc = mp - mpshift * width;
  double xlow = x - sc * gsigma;
  double xupp = x + sc * gsigma;
  double step = (xupp - xlow) / np;
  double sum = 0.0;

  for (double i = 1.0; i <= np / 2.0; i++) {
    double xx = xlow + (i - .5) * step;
    double fland = TMath::Landau(xx, mpc, width) / width;
    sum += fland * TMath::Gaus(x, xx, gsigma);

    xx = xupp - (i - .5) * step;
    fland = TMath::Landau(xx, mpc, width) / width;
    sum += fland * TMath::Gaus(x, xx, gsigma);
  }

  return area * step * sum * invsq2pi / gsigma;
}

class ProfiledPoissonNLL {
public:
  ProfiledPoissonNLL(
      const std::vector<double>& x,
      const std::vector<double>& counts,
      double area_lo,
      double area_hi)
      : x_(x), counts_(counts), area_lo_(area_lo), area_hi_(area_hi),
        unit_(x.size(), 0.0), last_area_(std::numeric_limits<double>::quiet_NaN()) {
    total_ = 0.0;
    for (double value : counts_) total_ += value;
  }

  double Eval(double width, double mp, double gsigma) {
    if (!(width > 0.0) || !(gsigma > 0.0) || !std::isfinite(mp)) {
      last_area_ = std::numeric_limits<double>::quiet_NaN();
      return std::numeric_limits<double>::infinity();
    }

    double qsum = 0.0;
    for (std::size_t i = 0; i < x_.size(); ++i) {
      double q = langaufun_value(x_[i], width, mp, 1.0, gsigma);
      if (!(q > 0.0) || !std::isfinite(q)) {
        last_area_ = std::numeric_limits<double>::quiet_NaN();
        return std::numeric_limits<double>::infinity();
      }
      unit_[i] = q;
      qsum += q;
    }
    if (!(qsum > 0.0) || !std::isfinite(qsum)) {
      last_area_ = std::numeric_limits<double>::quiet_NaN();
      return std::numeric_limits<double>::infinity();
    }

    double area = total_ / qsum;
    area = std::max(area_lo_, std::min(area_hi_, area));
    last_area_ = area;

    double nll = 0.0;
    for (std::size_t i = 0; i < x_.size(); ++i) {
      double mu = area * unit_[i];
      double n = counts_[i];
      if (!(mu > 0.0) || !std::isfinite(mu)) {
        return std::numeric_limits<double>::infinity();
      }
      if (n > 0.0) {
        nll += mu + n * std::log(n / mu) - n;
      } else {
        nll += mu;
      }
    }
    return nll;
  }

  double LastArea() const { return last_area_; }
  double TotalCount() const { return total_; }

private:
  std::vector<double> x_;
  std::vector<double> counts_;
  double area_lo_;
  double area_hi_;
  std::vector<double> unit_;
  double last_area_;
  double total_;
};

} // namespace yawl_lfhcal_langau
'''

_DECLARED = False


def declare_cpp() -> None:
    global _DECLARED
    if _DECLARED:
        return
    if not ROOT.gInterpreter.Declare(_CPP):
        raise RuntimeError("ROOT failed to compile the production Langau evaluator")
    _DECLARED = True


def load_model_histogram(model_path: Path) -> tuple[dict[str, Any], object, list[float], list[float]]:
    source = ROOT.TFile.Open(str(model_path), "READ")
    if not source or source.IsZombie():
        raise OSError(f"could not open {model_path}")

    metadata_named = source.Get("data_metadata")
    histogram = source.Get("input_histogram")
    if not histogram:
        histogram = source.Get("fit_hist")
    if not metadata_named or not histogram:
        keys = [key.GetName() for key in source.GetListOfKeys()]
        source.Close()
        raise ValueError(
            f"{model_path}: expected data_metadata and input_histogram/fit_hist; keys={keys}"
        )

    metadata = json.loads(metadata_named.GetTitle())
    hist = histogram.Clone(f"{histogram.GetName()}_production_langau")
    hist.SetDirectory(0)
    source.Close()

    actual_min, actual_max = map(float, metadata["actual_fit_range"])
    shifted_min = float(hist.GetXaxis().GetXmin())
    shift = actual_min - shifted_min

    centers: list[float] = []
    counts: list[float] = []
    for bin_number in range(1, hist.GetNbinsX() + 1):
        shifted_center = float(hist.GetBinCenter(bin_number))
        actual_center = shifted_center + shift
        if actual_min <= actual_center <= actual_max:
            centers.append(actual_center)
            counts.append(float(hist.GetBinContent(bin_number)))

    if not centers:
        raise ValueError(f"{model_path}: no histogram bins in the requested fit range")
    return metadata, hist, centers, counts


def parameter_bounds(metadata: dict[str, Any]) -> dict[str, tuple[float, float]]:
    raw = metadata.get("parameters", {})
    result: dict[str, tuple[float, float]] = {}
    for name in ("mpv", "landau_width", "gauss_sigma"):
        values = raw.get(name)
        if not isinstance(values, list) or len(values) != 2:
            raise ValueError(f"model metadata has no two-value bound for {name}")
        result[name] = (float(values[0]), float(values[1]))
    return result


def make_evaluator(
    centers: list[float],
    counts: list[float],
    area_lo: float = 1.0,
    area_hi: float | None = None,
):
    declare_cpp()
    total = float(sum(counts))
    if area_hi is None:
        area_hi = 5.0 * total
    xs = ROOT.std.vector("double")()
    ys = ROOT.std.vector("double")()
    for value in centers:
        xs.push_back(float(value))
    for value in counts:
        ys.push_back(float(value))
    evaluator = ROOT.yawl_lfhcal_langau.ProfiledPoissonNLL(
        xs, ys, float(area_lo), float(area_hi)
    )
    return evaluator


def expected_value(x: float, landau_width: float, mpv: float, area: float, gauss_sigma: float) -> float:
    declare_cpp()
    return float(
        ROOT.yawl_lfhcal_langau.langaufun_value(
            float(x), float(landau_width), float(mpv), float(area), float(gauss_sigma)
        )
    )


def evaluate_shape(evaluator, mpv: float, landau_width: float, gauss_sigma: float) -> tuple[float, float]:
    nll = float(evaluator.Eval(float(landau_width), float(mpv), float(gauss_sigma)))
    area = float(evaluator.LastArea())
    return nll, area
