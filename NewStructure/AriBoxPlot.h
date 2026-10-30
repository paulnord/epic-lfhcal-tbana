#ifndef ARI_BOX_PLOT_H
#define ARI_BOX_PLOT_H

// Display-only statistics. Never remove or alter input measurements.
#include <algorithm>
#include <cmath>
#include <limits>
#include <iterator>
#include <stdexcept>
#include <vector>

namespace AriBoxPlot {
struct Summary {
  double q1, median, q3, lowerFence, upperFence, lowWhisker, highWhisker;
  double minimum, maximum;
  std::size_t count, outlierCount;
  bool IsOutlier(double value) const {
    return value < lowerFence || value > upperFence;
  }
};

// Same unbinned, linear q*(n-1) convention as ComparisonWaveform.cc.
inline double QuantileSorted(const std::vector<double>& values, double q) {
  const double position = q * (values.size() - 1);
  const std::size_t low = static_cast<std::size_t>(std::floor(position));
  const std::size_t high = static_cast<std::size_t>(std::ceil(position));
  const double fraction = position - low;
  return values[low] * (1. - fraction) + values[high] * fraction;
}

inline Summary Summarize(std::vector<double> values) {
  if (values.empty()) throw std::invalid_argument("empty box-plot sample");
  for (double value : values)
    if (!std::isfinite(value))
      throw std::invalid_argument("non-finite box-plot sample; do not silently filter");
  std::sort(values.begin(), values.end());
  Summary s{};
  s.count = values.size();
  s.q1 = QuantileSorted(values, .25);
  s.median = QuantileSorted(values, .5);
  s.q3 = QuantileSorted(values, .75);
  const double iqr = s.q3 - s.q1;
  s.lowerFence = s.q1 - 1.5 * iqr;
  s.upperFence = s.q3 + 1.5 * iqr;
  // Equality to a fence is included. Whiskers are OBSERVED values, not fences.
  s.lowWhisker = *std::lower_bound(values.begin(), values.end(), s.lowerFence);
  s.highWhisker = *std::prev(std::upper_bound(values.begin(), values.end(), s.upperFence));
  s.minimum = values.front();
  s.maximum = values.back();
  s.outlierCount = std::count_if(values.begin(), values.end(),
                               [&s](double x) { return s.IsOutlier(x); });
  return s;
}

struct Range {
  double low, high;
  bool Contains(double value) const { return value >= low && value <= high; }
};

// Common metric axis across ALL settings: envelope of boxes and observed
// in-fence whiskers for main view; all actual values for companion. Including
// Q1/Q3 matters for sparse samples whose interpolated quartiles lie beyond
// the observed in-fence endpoints. Add 8%/12% padding.
// A nonnegative metric may start at zero, but negative data are never hidden
// by a zero clamp. Degenerate/empty inputs get deterministic usable ranges.
inline Range AxisRange(const std::vector<Summary>& summaries, bool zoom,
                       bool zeroFloor) {
  if (summaries.empty()) return {0., 1.};
  double low = std::numeric_limits<double>::infinity();
  double high = -low;
  double minimum = low;
  for (const auto& s : summaries) {
    low = std::min(low, zoom ? std::min(s.lowWhisker,s.q1) : s.minimum);
    high = std::max(high, zoom ? std::max(s.highWhisker,s.q3) : s.maximum);
    minimum = std::min(minimum, s.minimum);
  }
  if (!(high > low)) {
    const double padding = std::max(1., .1 * std::fabs(low));
    low -= padding;
    high += padding;
  }
  const double span = high - low;
  low -= .08 * span;
  high += .12 * span;
  if (zeroFloor && minimum >= 0.) low = 0.;
  return {low, high};
}

struct OffScaleCount { std::size_t below = 0, above = 0; };
inline OffScaleCount CountOffScale(const std::vector<double>& values, Range range) {
  OffScaleCount counts;
  for (double value : values) {
    if (value < range.low) ++counts.below;
    if (value > range.high) ++counts.above;
  }
  return counts;
}
}  // namespace AriBoxPlot
#endif
