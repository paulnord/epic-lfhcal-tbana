"""ROOT-free tests for the diagnostic report; not numerical ROOT validation."""
import math
import unittest
from fft_grid_report import GRID_METHODS, TARGET, summarize_probes


class GridReportTests(unittest.TestCase):
    def row(self, error, n=10000):
        return dict(method=f'fft{n}', n_fft=n, grid_spacing=265/(n-1),
                    max_abs_error_over_peak_8=error)

    def test_observed_failure_is_not_relabeled(self):
        rows = summarize_probes([self.row(.0011970336351142792), self.row(.0004, 32768)])
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0]['accuracy_target_met'])
        self.assertTrue(rows[1]['accuracy_target_met'])
        self.assertAlmostEqual(rows[0]['max_abs_error_percent_of_peak'], .11970336351142792)

    def test_nonfinite_rejected(self):
        for value in (math.nan, math.inf, -math.inf, -1.):
            with self.assertRaises(ValueError):
                summarize_probes([self.row(value)])

    def test_target_unchanged(self):
        self.assertEqual(TARGET, .001)
        self.assertTrue(summarize_probes([self.row(TARGET)])[0]['accuracy_target_met'])

    def test_grid_parity_diagnostic_only(self):
        even, odd = summarize_probes([self.row(.002), self.row(.0001, 10001)])
        self.assertAlmostEqual(even['predicted_even_grid_half_step_adc'], 265/9999/2)
        self.assertEqual(odd['predicted_even_grid_half_step_adc'], 0.)
        self.assertTrue(all(n*n <= 2**31-1 for _, _, n, _ in GRID_METHODS))


if __name__ == '__main__':
    unittest.main()
