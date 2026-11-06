"""Display math and saved-measurement reader regressions; ROOT checks skip if absent."""
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location('plot_all_scans', Path(__file__).with_name('plot_all_scans.py'))
plots = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plots)
try:
    import ROOT
except ImportError:
    ROOT = None


class BoxTests(unittest.TestCase):
    def test_quartiles_remain_unbinned_linear(self):
        self.assertEqual([plots.quantile([0, 0, 0, 1000], q) for q in (.25,.5,.75)], [0,0,250])

    def test_empty(self):
        self.assertIsNone(plots.box_summary([]))
        lo, hi = plots.plot_range([], [], 'fwhm', True)
        self.assertTrue(math.isfinite(lo) and math.isfinite(hi) and lo < hi)

    def test_singleton(self):
        s = plots.box_summary([7])
        self.assertEqual([s[k] for k in ('q1','median','q3','low','high')], [7]*5)
        lo, hi = plots.plot_range([s], [7], 'peak_time', True)
        self.assertLess(lo, 7)
        self.assertGreater(hi, 7)

    def test_inclusive_fences(self):
        s = plots.box_summary([0,1,2,3,6])
        self.assertEqual(s['upper_fence'], 6)
        self.assertEqual(s['high'], 6)
        self.assertEqual(plots.box_summary([0,1,2,3,6.01])['high'], 3)

    def test_whiskers_are_observed_values_not_fences(self):
        s = plots.box_summary([0,1,2,3,100])
        self.assertEqual((s['low'], s['high']), (0,3))
        self.assertEqual((s['lower_fence'], s['upper_fence']), (-2,6))

    def test_zero_iqr(self):
        s = plots.box_summary([2,2,2,2,100])
        self.assertEqual((s['low'], s['high']), (2,2))
        self.assertEqual((s['lower_fence'], s['upper_fence']), (2,2))

    def test_sparse_quartile_not_clipped(self):
        values = [0,0,0,1000]
        s = plots.box_summary(values)
        self.assertEqual(s['high'], 0)
        lo, hi = plots.plot_range([s], values, 'amplitude', True)
        self.assertLessEqual(lo, s['q1'])
        self.assertGreaterEqual(hi, s['q3'])
        self.assertLess(hi, 1000)

    def test_nonnegative_amplitude_main_starts_at_zero(self):
        v = [1,2,3,4,100]
        lo, hi = plots.plot_range([plots.box_summary(v)], v, 'amplitude', True)
        self.assertEqual(lo, 0)
        self.assertLess(hi, 100)

    def test_negative_observed_values_not_zero_clamped(self):
        v = [-4,-3,-2,-1]
        for main in (True, False):
            lo, hi = plots.plot_range([plots.box_summary(v)], v, 'amplitude', main)
            self.assertLessEqual(lo, min(v))
            self.assertGreaterEqual(hi, max(v))

    def test_full_range_keeps_every_value(self):
        v = [-100,0,1,2,3,1000]
        lo, hi = plots.plot_range([plots.box_summary(v)], v, 'peak_time', False)
        self.assertLessEqual(lo, min(v))
        self.assertGreaterEqual(hi, max(v))
        self.assertEqual(plots.offscale_counts(v, lo, hi), (0,0))

    def test_offscale_counts_actual_values_and_inclusive_axis_edges(self):
        self.assertEqual(plots.offscale_counts([-10,-1,0,0,1,2,3,4,5], 0,3), (2,2))
        self.assertEqual(plots.offscale_counts([], 0,3), (0,0))
        self.assertEqual(plots.offscale_counts([0,0,3,3], 0,3), (0,0))

    def test_input_values_unchanged(self):
        v = [100,1,2,0,3]
        original = list(v)
        s = plots.box_summary(v)
        plots.plot_range([s], v, 'amplitude', True)
        plots.offscale_counts(v, 0, 10)
        self.assertEqual(v, original)


@unittest.skipIf(ROOT is None, 'PyROOT unavailable; native saved-histogram tests not run')
class SavedHistogramTests(unittest.TestCase):
    def make_file(self, path, status=0, amplitude=5, fwhm=2, peak_time=-47.5):
        f = ROOT.TFile(str(path), 'RECREATE')
        histograms = {}
        for key, _, name in plots.METRICS:
            histograms[key] = ROOT.TH1D(name, '', 2048, -.5,2047.5)
        statuses = ROOT.TH1D('hWaveformMeasurementStatusVsCellID','',2048,-.5,2047.5)
        counts = ROOT.TH1D('hWaveformMeasurementStatusCounts','',10,.5,10.5)
        cell = plots.CELLS[0]
        statuses.SetBinContent(cell+1, status+1)
        for key, value in [('amplitude',amplitude),('fwhm',fwhm),('peak_time',peak_time)]:
            histograms[key].SetBinContent(cell+1, value)
        for h in [statuses,counts,*histograms.values()]: h.Write()
        f.Close()

    def test_narrow_width_negative_time_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'input.root'; self.make_file(path)
            rows = plots.read_measurements(ROOT,path,{})
            self.assertEqual((rows[0]['amplitude'],rows[0]['fwhm'],rows[0]['peak_time']), (5,2,-47.5))
            self.assertIsNone(rows[1]['fwhm'])

    def test_invalid_width_not_zero_or_new_cut(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'input.root'; self.make_file(path,status=6,amplitude=1100,fwhm=0)
            row = plots.read_measurements(ROOT,path,{})[0]
            self.assertEqual(row['status'],6)
            self.assertEqual(row['amplitude'],1100)
            self.assertIsNone(row['fwhm'])

    def test_unfilled_metrics_stay_missing(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'input.root'; self.make_file(path,status=-1,amplitude=0,fwhm=0,peak_time=0)
            row = plots.read_measurements(ROOT,path,{})[0]
            self.assertEqual(row['status'],-1)
            self.assertTrue(all(row[key] is None for key,_,_ in plots.METRICS))

    def test_existing_nonpositive_valid_width_rejection_retained(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'input.root'; self.make_file(path,fwhm=0)
            with self.assertRaisesRegex(ValueError, 'Nonpositive saved valid measurement'):
                plots.read_measurements(ROOT,path,{})


if __name__ == '__main__': unittest.main()
