"""Standard-library tests for orchestration; these do not simulate ROOT fitting."""
import contextlib
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import run_adaptive_refits as runner


class Tests(unittest.TestCase):
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
row=dict(integrator=mode,result_valid='0',cov_status='2',n_calls='9',min_fcn='12.3',edm='0.1',fit_status='4000',legacy_fit_gate_pass='0',numerics_pass='0',numerics_complete='0',adaptive_peak='nan',adaptive_fwhm='nan',peak='nan',fwhm='nan',width='0.1',gsigma='29',boundary_parameters='Width:lower',numerics_error='MOCK only')
with open(out,'w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=row)
    w.writeheader(); w.writerow(row); w.writerow(row)
Path(args[args.index('--results-root')+1]).write_text('MOCK, not a ROOT file')
''')
            fake.chmod(0o755)
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
            self.assertEqual(meta['cases'][1]['argv'][meta['cases'][1]['argv'].index('--quad-rtol')+1], '1e-8')
            self.assertEqual(meta['cases'][2]['argv'][meta['cases'][2]['argv'].index('--quad-rtol')+1], '1e-10')
            again=subprocess.run([sys.executable, runner.__file__, '--work', str(work),
                                  '--fitter', str(fake), '--out', str(out)], capture_output=True, text=True)
            self.assertNotEqual(again.returncode,0)

    def test_reject_bad_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.csv'; path.write_text('not,the,header\n1,2,3\n')
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                runner.show([path])

if __name__ == '__main__':
    unittest.main()
