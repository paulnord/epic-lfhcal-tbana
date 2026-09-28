#!/usr/bin/env python3
"""Odd-grid selection/reporting regressions; no ROOT numerical claims."""
import contextlib
import csv
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark as b


class FakeFunction:
    def __init__(self, area=1.):
        self.area = area.area if isinstance(area, FakeFunction) else area

    def Clone(self, name):
        raise AssertionError('Use the live TF1 copy constructor, not streamed Clone')

    def SetName(self, name):
        self.name = name

    def Eval(self, x):
        return self.area

    def SetParameter(self, index, value):
        if index != 2:
            raise AssertionError('This double only models the area lifetime check')
        self.area = value


def unsafe_grid(*args):
    raise ValueError('Oversized grid rejected by test double')


class OddGridTests(unittest.TestCase):
    def test_candidates_are_safe_odd_and_named_explicitly(self):
        actual = [m for m in b.METHODS if m[1] == 'fft']
        self.assertEqual(actual, [
            ('fft10001_odd', 'fft', 10001, 1.),
            ('fft16385_odd', 'fft', 16385, 1.),
            ('fft32769_odd', 'fft', 32769, 1.),
            ('fft32769_odd_wide', 'fft', 32769, 2.),
        ])
        self.assertEqual(len({m[0] for m in b.METHODS}), len(b.METHODS))
        self.assertTrue(all(n % 2 == 1 and 1000 <= n <= b.MAX_SAFE_FFT_POINTS
                            and n*n <= 2**31-1 for _, _, n, _ in actual))

    def test_padding_pair_has_equal_spacing(self):
        methods = {m[0]: m for m in b.METHODS}
        small = methods['fft16385_odd']
        wide = methods['fft32769_odd_wide']
        for domain_width in (265., 980., 3500.):
            self.assertEqual(domain_width * small[3] / (small[2]-1),
                             domain_width * wide[3] / (wide[2]-1))

    def test_model_contract_and_unsafe_guard_unchanged(self):
        self.assertEqual(b.PAR_NAMES, ('landau_width','mpv','area','gaussian_sigma'))
        self.assertEqual(b.FIT_OPTIONS, 'QRLMNS0')
        self.assertEqual(b.MAX_SAFE_FFT_POINTS, math.isqrt(2**31-1))
        self.assertIn(('adaptive5','adaptive5',0,1.), b.METHODS)
        self.assertIn(('legacy100','legacy100',0,1.), b.METHODS)
        with self.assertRaises(ValueError):
            b.factory(None, {}, ('unsafe','fft',65536,1.), 'unsafe')

    def test_passing_self_test_uses_odd_copy_control(self):
        rows = [dict(method=name,n_fft=n,max_abs_error_over_peak_8=1e-3)
                for name,kind,n,_ in b.METHODS if kind == 'fft']
        fake_root = SimpleNamespace(
            lfhcal=SimpleNamespace(fft_experiment=SimpleNamespace(make=unsafe_grid)),
            TF1=FakeFunction,
            SetOwnership=lambda *args: None,
            gROOT=SimpleNamespace(GetVersion=lambda: 'test double'),
        )
        with patch.object(b, 'probe', return_value=rows), \
             patch.object(b, 'factory', return_value=(FakeFunction(),0.,1.)) as factory, \
             patch.object(b, 'PROGRESS_PATH', None), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            b.self_test(fake_root)
        self.assertEqual(factory.call_args.args[2][0], 'fft32769_odd')
        self.assertEqual(output.getvalue().count('PASS,'), 4)
        self.assertIn('copy ratio=1.0, area ratio=2.0', output.getvalue())

    def test_accuracy_miss_still_fails_after_all_rows_saved_and_printed(self):
        rows = [dict(method='fft10001_odd',n_fft=10001,
                     max_abs_error_over_peak_8=0.0011970336351142792),
                dict(method='fft32769_odd',n_fft=32769,
                     max_abs_error_over_peak_8=0.00003066579)]
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b,'PROGRESS_PATH',Path(d)/'progress.json'), \
                 patch.object(b,'probe',return_value=rows), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(RuntimeError,'smoke check failed'):
                    b.self_test(None)
            with (Path(d)/'probes.csv').open() as handle:
                stored = list(csv.DictReader(handle))
            self.assertEqual(len(stored),2)
            self.assertIn('fft10001_odd: FAIL',output.getvalue())
            self.assertIn('fft32769_odd: PASS',output.getvalue())
            self.assertEqual(float(stored[0]['max_abs_error_over_peak_8']),
                             rows[0]['max_abs_error_over_peak_8'])

    def test_invalid_discrepancy_is_fatal(self):
        for value in (float('nan'),float('inf'),-1.):
            with self.subTest(value=value):
                rows = [dict(method='fft10001_odd',n_fft=10001,
                             max_abs_error_over_peak_8=value)]
                with patch.object(b,'PROGRESS_PATH',None), \
                     patch.object(b,'probe',return_value=rows), \
                     contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(RuntimeError):
                        b.self_test(None)


    def run_copy_control(self, constructor, directory=None):
        rows = [dict(method='fft32769_odd',n_fft=32769,
                     max_abs_error_over_peak_8=3e-5)]
        fake_root = SimpleNamespace(
            lfhcal=SimpleNamespace(fft_experiment=SimpleNamespace(make=unsafe_grid)),
            TF1=constructor,
            SetOwnership=lambda *args: None,
            gROOT=SimpleNamespace(GetVersion=lambda: 'test double'),
        )
        progress = Path(directory)/'progress.json' if directory else None
        with patch.object(b,'probe',return_value=rows), \
             patch.object(b,'factory',side_effect=lambda *args: (FakeFunction(),0.,1.)), \
             patch.object(b,'PROGRESS_PATH',progress), \
             contextlib.redirect_stdout(io.StringIO()):
            b.self_test(fake_root)

    def test_frozen_copy_still_fails_with_values_saved(self):
        class FrozenCopy(FakeFunction):
            def SetParameter(self, index, value):
                pass  # Deliberately emulate a serialized, sampled curve.
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError,'live copied callback'):
                self.run_copy_control(FrozenCopy,directory)
            diagnostic = json.loads((Path(directory)/'copy-lifetime.json').read_text())
        self.assertEqual(diagnostic['area_ratio'],1.)
        self.assertEqual(diagnostic['expected_area_ratio'],2.)
        self.assertEqual(diagnostic['tolerance'],1e-10)

    def test_nonfinite_live_copy_is_rejected(self):
        class InvalidCopy(FakeFunction):
            def Eval(self, x):
                return math.nan if self.area==2. else self.area
        with self.assertRaisesRegex(ValueError,'nonfinite'):
            self.run_copy_control(InvalidCopy)

    def test_live_copy_must_preserve_original_value(self):
        with self.assertRaisesRegex(RuntimeError,'live copied callback'):
            self.run_copy_control(lambda source: FakeFunction(source.area*1.1))


if __name__ == '__main__':
    unittest.main()
