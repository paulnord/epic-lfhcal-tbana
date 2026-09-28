#!/usr/bin/env python3
"""Report FFT resolution errors without running fits or weakening acceptance tests.

Uses the existing benchmark's identical ordinary control and +/-8-sigma
reference. Compare even/odd sample counts to diagnose TF1Convolution's grid
centering. Exit zero means the report completed, NOT that every grid passed.
The production adapter, benchmark self-test, and 0.1% accuracy target are unchanged.
"""
import argparse
import math
from pathlib import Path
import sys

TARGET = 1e-3
GRID_METHODS = (
    ('fft10000', 'fft', 10000, 1.),
    ('fft10001_odd', 'fft', 10001, 1.),
    ('fft16384', 'fft', 16384, 1.),
    ('fft16385_odd', 'fft', 16385, 1.),
    ('fft32768', 'fft', 32768, 1.),
    ('fft32769_odd', 'fft', 32769, 1.),
    ('fft32768_wide', 'fft', 32768, 2.),
    ('fft32769_odd_wide', 'fft', 32769, 2.),
)


def summarize_probes(rows):
    """Keep every measured miss visible; nonfinite values cannot pass."""
    result = []
    for row in rows:
        error = float(row['max_abs_error_over_peak_8'])
        dx = float(row['grid_spacing'])
        if not (math.isfinite(error) and error >= 0 and math.isfinite(dx) and dx > 0):
            raise ValueError(f"Invalid numerical check for {row['method']}")
        n = int(row['n_fft'])
        result.append({
            'method': row['method'], 'n_fft': n, 'grid_spacing_adc': dx,
            'max_abs_error_over_peak_8': error,
            'max_abs_error_percent_of_peak': 100 * error,
            'target_error_over_peak': TARGET,
            'accuracy_target_met': error <= TARGET,
            # Source-derived expectation for the endpoint-grid / integer-shift
            # implementation. This is a hypothesis to test, NOT a correction
            # applied to either curve or fit, and is version-dependent.
            'predicted_even_grid_half_step_adc': dx/2 if n % 2 == 0 else 0.,
        })
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        ap.error('Output directory must be empty; preserve earlier reports')

    # ROOT is imported only by this existing loader, not by module import/tests.
    import benchmark as b
    b.PROGRESS_PATH = out/'progress.json'
    here = Path(__file__).resolve().parent
    R = b.load_root(here)
    for _, _, n, _ in GRID_METHODS:
        R.lfhcal.convolution_benchmark.requireFFT(n)

    case = dict(case_id='synthetic_control', fit_lo=-5., fit_hi=100.,
                lower=[.1, 1., .01, .005], upper=[20., 80., 100., 10.],
                seed=[3., 30., 1., 5.])
    b.write_json(out/'manifest.json', {
        'root_version': R.gROOT.GetVersion(), 'argv': sys.argv,
        'case': case, 'methods': GRID_METHODS, 'accuracy_target': TARGET,
        'diagnostic_only': True, 'runs_minimization': False,
        'reference_numerics_base': b.BASE_COMMIT,
        'grid_hypothesis_source': 'ROOT TF1Convolution::MakeFFTConv',
    })
    rows = b.probe(R, case, case['seed'], 'ordinary', GRID_METHODS)
    # Save ALL measurements before interpreting any accuracy failures.
    b.write_csv(out/'probes.csv', rows)
    checks = summarize_probes(rows)
    b.write_json(out/'summary.json', {
        'report_complete': True,
        'accuracy_target': TARGET,
        'all_grids_meet_target': all(r['accuracy_target_met'] for r in checks),
        'results': checks,
    })
    print('\nOrdinary fixed-parameter control; NO FITS', flush=True)
    print('method                    points     dx (ADC)   error (% of peak)   0.1% target', flush=True)
    for row in checks:
        status = 'PASS' if row['accuracy_target_met'] else 'FAIL'
        print(f"{row['method']:25s} {row['n_fft']:6d} "
              f"{row['grid_spacing_adc']:12.6g} "
              f"{row['max_abs_error_percent_of_peak']:19.7g}   {status}", flush=True)
    print(f'\nAll measurements saved: {out}/probes.csv', flush=True)
    print('Report complete, not production certification. Accuracy failures remain FAIL.', flush=True)
    print('No parameter shift, normalization correction, or tolerance relaxation was applied.', flush=True)


if __name__ == '__main__':
    main()
