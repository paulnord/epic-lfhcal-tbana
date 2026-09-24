"""Standard-library tests for orchestration; these do not simulate ROOT fitting."""
import contextlib
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import run_adaptive_refits as runner


class Tests(unittest.TestCase):
    def fixture(self, work, behavior="normal"):
        for sub, name in [("refine1", "rawHGCROC_wPedwMuon_wBC_ImpR_194_calib.txt"),
                          ("refine2", "rawHGCROC_wPedwMuon_wBC_Imp2R_194_calib.txt"),
                          ("refine2", "rawHGCROC_wPedwMuon_wBC_Imp2R_194_Hists.root")]:
            (work / sub).mkdir(exist_ok=True)
            (work / sub / name).write_text("MOCK input, not scientific data\n")
        fake = work / "mock_fitter"
        fake.write_text('''#!/usr/bin/env python3
import sys, csv
from pathlib import Path
args=sys.argv
out=args[args.index('--csv')+1]
mode=args[args.index('--integrator')+1]
behavior=''' + repr(behavior) + '''
if behavior == 'fail_cap' and '--gsigma-high' in args:
    print('MOCK cap process failure; prior outputs must survive', flush=True)
    sys.exit(7)
if behavior == 'bad_csv':
    Path(out).write_text('not,the,header\\n1,2,3\\n1,2,3\\n')
    sys.exit(0)
row=dict(integrator=mode,result_valid='0',cov_status='2',n_calls='9',min_fcn='12.3',edm='0.1',fit_status='4000',legacy_fit_gate_pass='0',numerics_pass='0',numerics_complete='0',adaptive_peak='nan',adaptive_fwhm='nan',peak='nan',fwhm='nan',width='0.1',gsigma='29',boundary_parameters='Width:lower',numerics_error='MOCK only')
with open(out,'w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=row)
    w.writeheader(); w.writerow(row); w.writerow(row)
Path(args[args.index('--results-root')+1]).write_text('MOCK, not a ROOT file')
if behavior == 'mutate_hist':
    Path(args[1]).write_text('MOCK mutation of temporary test input only')
''')
        fake.chmod(0o755)
        return fake

    def run_runner(self, work, fake, out, *options):
        command = [sys.executable, runner.__file__, '--fitter', str(fake)]
        if work is not None:
            command += ['--work', str(work)]
        if out is not None:
            command += ['--out', str(out)]
        return subprocess.run(command + list(options), capture_output=True, text=True)

    def assert_case_timing(self, meta):
        for case in meta['cases']:
            self.assertGreaterEqual(case['elapsed_seconds'], 0)
            started = datetime.datetime.fromisoformat(case['started_utc'])
            finished = datetime.datetime.fromisoformat(case['finished_utc'])
            self.assertEqual(started.utcoffset(), datetime.timedelta(0))
            self.assertEqual(finished.utcoffset(), datetime.timedelta(0))
            self.assertGreaterEqual(finished, started)

    def test_missing_number_not_zero(self):
        self.assertEqual(runner.number("nan"), "nan")
        self.assertEqual(runner.number("ERROR"), "ERROR")
        self.assertEqual(runner.number("inf"), "inf")

    def test_missing_input_fails(self):
        result = subprocess.run([sys.executable, runner.__file__, "--work", "/no-such-cell903-test"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing input", result.stderr)

    def test_three_cases_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            fake = self.fixture(work)
            out=work / "output"
            result=subprocess.run([sys.executable, runner.__file__, '--work', str(work),
                                   '--fitter', str(fake), '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('nan nan', result.stdout)
            self.assertIn('ERROR', result.stdout)
            meta=json.loads((out/'run.json').read_text())
            self.assertEqual(len(meta['cases']),3)
            self.assertTrue(all(case['returncode']==0 for case in meta['cases']))
            self.assertTrue(all(case['argv'].count('--calib')==2 for case in meta['cases']))
            self.assert_case_timing(meta)
            expected_inputs = {str(p.resolve()) for p in [fake,
                work / 'refine1/rawHGCROC_wPedwMuon_wBC_ImpR_194_calib.txt',
                work / 'refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_calib.txt',
                work / 'refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_Hists.root']}
            self.assertEqual(set(meta['file_sha256']), expected_inputs)
            for path, expected_hash in meta['file_sha256'].items():
                self.assertEqual(expected_hash, hashlib.sha256(Path(path).read_bytes()).hexdigest())
            self.assertEqual(meta['histogram']['sha256'],
                             meta['file_sha256'][meta['histogram']['path']])
            code = meta['code']
            if code['git_commit'] is not None:
                self.assertRegex(code['git_commit'], r'^[0-9a-f]{40,64}$')
                patch = Path(code['diff_path'])
                self.assertEqual(patch.parent, out.resolve())
                self.assertEqual(code['diff_sha256'], hashlib.sha256(patch.read_bytes()).hexdigest())
            else:
                self.assertIn('error', code)
            self.assertEqual(meta['cases'][1]['argv'][meta['cases'][1]['argv'].index('--quad-rtol')+1], '1e-8')
            self.assertEqual(meta['cases'][2]['argv'][meta['cases'][2]['argv'].index('--quad-rtol')+1], '1e-10')
            again=subprocess.run([sys.executable, runner.__file__, '--work', str(work),
                                  '--fitter', str(fake), '--out', str(out)], capture_output=True, text=True)
            self.assertNotEqual(again.returncode,0)

    def test_bound_experiment_only_changes_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp).resolve()
            fake = self.fixture(work)
            hist = work / 'saved baseline.root'
            hist.write_text('MOCK saved source histogram, not a ROOT file')
            out = work / 'results'
            result = self.run_runner(work, fake, out, '--experiment', 'gsigma-bound',
                                     '--histogram', str(hist), '--histogram-key', 'source_histogram')
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = json.loads((out / 'run.json').read_text())
            self.assertEqual(meta['experiment'], 'gsigma-bound')
            self.assertEqual(meta['histogram']['path'], str(hist))
            self.assertEqual(meta['histogram']['key'], 'source_histogram')
            self.assertEqual(meta['histogram']['sha256'], hashlib.sha256(hist.read_bytes()).hexdigest())
            self.assertEqual([c['case'] for c in meta['cases']],
                             ['adaptive_noM_1e-10', 'adaptive_sigma58'])
            baseline, extended = [c['argv'] for c in meta['cases']]
            expected = [str(fake), str(hist), '--calib',
                        str(work / 'refine1/rawHGCROC_wPedwMuon_wBC_ImpR_194_calib.txt'),
                        '--calib', str(work / 'refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_calib.txt'),
                        '--hist', 'source_histogram', '--integrator', 'adaptive',
                        '--quad-rtol', '1e-10', '--fit-option', 'QRLN0']
            self.assertEqual(baseline[:-4], expected)
            self.assertEqual(extended[:-4], expected + ['--gsigma-high', '58.129'])
            for command in (baseline, extended):
                self.assertEqual(command[-4], '--csv')
                self.assertEqual(command[-2], '--results-root')
                self.assertEqual(Path(command[-3]).parent, out)
                self.assertEqual(Path(command[-1]).parent, out)
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            again = self.run_runner(work, fake, out, '--experiment', 'gsigma-bound')
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_bound_experiment_requires_explicit_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            fake = self.fixture(work)
            before = set(work.iterdir())
            result = self.run_runner(work, fake, None, '--experiment', 'gsigma-bound')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--out is required', result.stderr)
            self.assertEqual(set(work.iterdir()), before)

    def test_failed_subprocess_preserves_baseline_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            fake = self.fixture(work, 'fail_cap')
            out = work / 'results'
            result = self.run_runner(work, fake, out, '--experiment', 'gsigma-bound')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('failed with exit 7', result.stderr)
            self.assertIn('MOCK cap process failure', (out / 'adaptive_sigma58.log').read_text())
            self.assertEqual(len(runner.read_rows(out / 'adaptive_noM_1e-10.csv')), 2)
            self.assertTrue((out / 'adaptive_noM_1e-10.root').is_file())
            meta = json.loads((out / 'run.json').read_text())
            self.assertEqual([c['returncode'] for c in meta['cases']], [0, 7])
            self.assert_case_timing(meta)

    def test_explicit_inputs_without_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp).resolve()
            fake = self.fixture(work)
            hist = work / 'compact.root'
            hist.write_text('MOCK compact histogram')
            c1, c2 = work / 'first seed.txt', work / 'second seed.txt'
            c1.write_text('MOCK first explicit seed')
            c2.write_text('MOCK second explicit seed')
            out = work / 'results'
            result = self.run_runner(None, fake, out, '--experiment', 'gsigma-bound',
                                     '--histogram', str(hist), '--histogram-key', 'source_histogram',
                                     '--calib', str(c1), '--calib', str(c2))
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = json.loads((out / 'run.json').read_text())
            for case in meta['cases']:
                self.assertEqual(case['argv'][:8], [str(fake), str(hist), '--calib', str(c1),
                                                   '--calib', str(c2), '--hist', 'source_histogram'])
            self.assertEqual(set(meta['file_sha256']), {str(p) for p in (fake, hist, c1, c2)})

    def test_explicit_inputs_require_two_calibrations_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            fake = self.fixture(work)
            hist = work / 'refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_194_Hists.root'
            calib = work / 'refine1/rawHGCROC_wPedwMuon_wBC_ImpR_194_calib.txt'
            for count in (1, 3):
                with self.subTest(count=count):
                    result = self.run_runner(None, fake, work / 'results', '--histogram', str(hist),
                                             *(['--calib', str(calib)] * count))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('--calib must be supplied exactly twice', result.stderr)
            result = self.run_runner(None, fake, None, '--histogram', str(hist),
                                     '--calib', str(calib), '--calib', str(calib))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--out is required when --work is omitted', result.stderr)
            self.assertFalse((work / 'results').exists())

    def test_histogram_mutation_is_detected_before_next_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            fake = self.fixture(work, 'mutate_hist')
            out = work / 'results'
            result = self.run_runner(work, fake, out)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('histogram input changed during the experiment', result.stderr)
            meta = json.loads((out / 'run.json').read_text())
            self.assertEqual(len(meta['cases']), 1)
            hist = Path(meta['histogram']['path'])
            self.assertNotEqual(meta['histogram']['sha256'], hashlib.sha256(hist.read_bytes()).hexdigest())
            self.assert_case_timing(meta)

    def test_malformed_output_stops_before_next_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            fake = self.fixture(work, 'bad_csv')
            out = work / 'results'
            result = self.run_runner(work, fake, out)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('not an adaptive-refit CSV', result.stderr)
            meta = json.loads((out / 'run.json').read_text())
            self.assertEqual(len(meta['cases']), 1)
            self.assertTrue((out / 'fixed100.csv').is_file())

    def test_reject_truncated_csv_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            fake = self.fixture(work)
            out = work / 'results'
            result = self.run_runner(work, fake, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            path = out / 'adaptive_1e-10.csv'
            lines = path.read_text().splitlines()
            path.write_text(lines[0] + '\n' + lines[1].rsplit(',', 1)[0] + '\n')
            with self.assertRaisesRegex(ValueError, 'malformed CSV row'):
                runner.read_rows(path)

    def test_reject_bad_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.csv'; path.write_text('not,the,header\n1,2,3\n')
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                runner.show([path])

if __name__ == '__main__':
    unittest.main()
