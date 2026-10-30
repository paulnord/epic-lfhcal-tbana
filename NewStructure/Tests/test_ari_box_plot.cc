#include "../AriBoxPlot.h"
#include <stdexcept>
#define CHECK(condition) do { if (!(condition)) throw std::runtime_error(#condition); } while (false)
#include <iostream>
#include <iomanip>
#include <string>

int main(int argc, char** argv) {
  using namespace AriBoxPlot;
  if (argc > 1 && std::string(argv[1]) == "--ranges") {
    std::size_t groups; bool zeroFloor;
    std::cout << std::setprecision(17);
    while (std::cin >> groups >> zeroFloor) {
      std::vector<Summary> summaries;
      for (std::size_t i = 0; i < groups; ++i) {
        std::size_t count; std::cin >> count;
        std::vector<double> values(count);
        for (double& value : values) std::cin >> value;
        summaries.push_back(Summarize(values));
      }
      for (bool zoom : {true, false}) {
        const auto r = AxisRange(summaries, zoom, zeroFloor);
        std::cout << r.low << ' ' << r.high << ' ';
      }
      std::cout << '\n';
    }
    return 0;
  }
  // CLI for independent real-data cross-checks and reproducible preview input.
  if (argc > 1 && std::string(argv[1]) == "--summarize") {
    std::size_t count;
    std::cout << std::setprecision(17);
    while (std::cin >> count) {
      std::vector<double> values(count);
      for (double& value : values) std::cin >> value;
      const auto s = Summarize(values);
      std::cout << s.q1 << ' ' << s.median << ' ' << s.q3 << ' '
                << s.lowerFence << ' ' << s.upperFence << ' '
                << s.lowWhisker << ' ' << s.highWhisker << ' '
                << s.minimum << ' ' << s.maximum << ' ' << s.outlierCount << '\n';
    }
    return 0;
  }
  const std::vector<double> input{100, 0, 4, 3, 2, 1};
  const auto s = Summarize(input);
  CHECK(input.front() == 100); // caller input untouched
  CHECK(s.q1 == 1.25 && s.median == 2.5 && s.q3 == 3.75);
  CHECK(s.lowerFence == -2.5 && s.upperFence == 7.5);
  CHECK(s.lowWhisker == 0 && s.highWhisker == 4 && s.outlierCount == 1);
  const auto exact = Summarize({-3, 0, 0, 1, 2, 2, 5});
  CHECK(exact.lowerFence == -3 && exact.upperFence == 5);
  CHECK(!exact.IsOutlier(-3) && !exact.IsOutlier(5));
  CHECK(exact.lowWhisker == -3 && exact.highWhisker == 5);
  const auto zero = Summarize({4, 4, 4, 4, 100});
  CHECK(zero.q1 == 4 && zero.q3 == 4 && zero.outlierCount == 1);
  CHECK(zero.lowWhisker == 4 && zero.highWhisker == 4);
  const auto singleton = Summarize({7});
  CHECK(singleton.outlierCount == 0 && singleton.lowWhisker == 7);
  CHECK(AxisRange({singleton}, true, false).Contains(7));
  CHECK(AxisRange({}, true, false).low == 0);
  const auto sparse = Summarize({0, 0, 0, 1000});
  CHECK(sparse.highWhisker == 0 && sparse.q3 == 250);
  CHECK(AxisRange({sparse}, true, true).Contains(sparse.q3));
  auto both = CountOffScale({-1, 0, 0.5, 1, 2}, {0, 1});
  CHECK(both.below == 1 && both.above == 1); // edges inclusive
  CHECK(CountOffScale(input, AxisRange({s}, false, false)).above == 0);
  CHECK(CountOffScale(input, AxisRange({s}, true, false)).above == 1);
  CHECK(AxisRange({exact}, false, true).low < -3); // no hidden negative value
  bool emptyThrows = false, nonfiniteThrows = false;
  try { Summarize({}); } catch (const std::invalid_argument&) { emptyThrows = true; }
  try { Summarize({0, std::numeric_limits<double>::quiet_NaN()}); }
  catch (const std::invalid_argument&) { nonfiniteThrows = true; }
  CHECK(emptyThrows && nonfiniteThrows);
  std::cout << "PASS: quartiles, observed whiskers, inclusive fences, zero IQR, "
               "singleton/empty, both tails, exact edges, negative values, input preservation.\n";
}
