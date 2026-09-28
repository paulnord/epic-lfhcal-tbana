# Live TF1 copying is not Clone serialization

The BNL self-test at `3ea70ad` passed the ordinary odd-grid accuracy checks,
then stopped with `Area mapping or copied callback ownership failed`.
The test used `f.Clone(...)` and expected changing parameter 2 to double the
function after deleting the original. That is the wrong operation for testing
an executable C++ callback.

ROOT's `TF1::Clone` calls `TNamed::Clone`, which uses streaming. For a TF1 built
from a C++ callback, the streamed object preserves sampled function values,
not a serializable implementation of the callback. It is a curve snapshot,
not an object whose parameters can be changed and refitted as before.
ROOT's C++ copy constructor instead calls `TF1::Copy`, which copies the functor.

The self-test now uses `ROOT.TF1(f)` (the C++ copy constructor). It still deletes
the original before doubling the area and evaluating the copy. It additionally
checks that the copied initial value agrees with the original. The original
1e-10 ratio tolerance is unchanged; nonfinite, frozen or distorted copies fail.
`self-test/copy-lifetime.json` records the original/before/after values and ratios,
and the log prints them before applying the checks.

This change only corrects the test. No change is made to `TF1Langau.h`, the FFT
size/domain, physical parameters, minimizer, curve-accuracy tolerance, or real
histogram fitting. `TH1::Clone` used to duplicate the input histograms remains
appropriate and is unchanged. Disk round-trip and parameterized reconstruction
of stored callback TF1s remain separate checks before production adoption.

The focused Python tests deliberately reject calling Clone, reject a frozen
copy, reject nonfinite copied evaluations, and reject an altered initial value.
They use test doubles, not ROOT; the real copy-constructor/lifetime test must
still pass in the BNL ROOT 6.40.04 environment.

Primary references:
- https://root.cern/doc/master/TF1_8cxx_source.html (TF1 copy constructor, Copy, Clone)
- https://root-forum.cern.ch/t/problem-with-cloning-and-fitting-tgraph/57418 (ROOT maintainer's explanation)
