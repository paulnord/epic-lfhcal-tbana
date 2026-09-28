#!/usr/bin/env python3
"""Fast tests of setup/reporting and the external watchdog; ROOT is not needed."""
import csv
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
import benchmark as b
import run_benchmark as runner


class Histogram:
    def __init__(self, entries=100): self.entries=entries
    def GetEntries(self): return self.entries
    def FindBin(self,x): return int(math.floor(x))+101
    def GetBinCenter(self,i): return i-100.5
    def GetBinContent(self,i): return 0 if i==106 else 10
    def Integral(self,lo,hi): return sum(self.GetBinContent(i) for i in range(lo,hi+1))


class BenchmarkTests(unittest.TestCase):
    def test_original_floor_and_valley(self):
        s = b.original_setup(Histogram(),1.,30.,5.7,5)
        self.assertEqual(s['lower'][3],.01)
        self.assertEqual(s['upper'][3],30.)
        self.assertEqual(s['fit_lo'],5.5)
        self.assertEqual(s['fit_hi'],90.)
        self.assertEqual(s['seed'][1],30.)
        self.assertEqual(s['lower'][1],5.5)

    def test_high_voltage_long_segment(self):
        s = b.original_setup(Histogram(),2.,30.,6.7,10)
        self.assertAlmostEqual(s['fit_hi'],144.)
        self.assertAlmostEqual(s['upper'][1],126.)
        self.assertEqual(s['upper'][3],200.)
        self.assertEqual(s['lower'][3],.02)

    def test_low_voltage_original_limits(self):
        s = b.original_setup(Histogram(),1.,30.,3.7,1)
        self.assertEqual(s['lower'][0],.01)
        self.assertEqual(s['lower'][3],.001)

    def test_invalid_pedestal(self):
        with self.assertRaises(ValueError): b.original_setup(Histogram(),0.,30.,5.7,5)

    def test_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'map.txt'
            p.write_text('sumOpt 2\n0 11 2 F001 1 0 2 0 -10 -10 5\n')
            self.assertEqual(b.read_segments(p),{130:5})

    def test_calib_missing_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'calib.txt'
            line='0 0 0 0 0 80 1 80 0.2 30 20 -1000 -1000 -64 -1000 -64 -1000 3\n'
            p.write_text('# Vov: 5.7\n'+line)
            vov,avg,rows=b.read_calib(p)
            self.assertEqual((vov,avg,rows[0]['ped']),(5.7,30.,1.))
            p.write_text(p.read_text()+line)
            with self.assertRaises(ValueError): b.read_calib(p)

    def test_selection_independent_of_fit_saved(self):
        result=b.selected_cells('e1',{1:Histogram(25),2:Histogram(2000)},
                               {1:{'bc':3},2:{'bc':3}},'survey')
        self.assertEqual(result[1],'lowest_entries')
        self.assertEqual(result[2],'highest_entries')
        self.assertIn(896,result)

    def test_csv_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.csv'
            b.write_csv(p,[{'x':float('nan'),'y':None,'z':0}])
            with p.open() as f: row=next(csv.DictReader(f))
            self.assertEqual(row,{'x':'?','y':'?','z':'0'})
            self.assertFalse(p.with_name('a.csv.tmp').exists())

    def test_paired_timing(self):
        rows=[dict(method='adaptive5',case_id='e1:903',repeat=0,fit_wall_s=4.,status=0),
              dict(method='fft32768',case_id='e1:903',repeat=0,fit_wall_s=2.,status=1)]
        summary=b.summarize(rows)
        self.assertEqual(summary['fft32768']['paired_median_speedup'],2.)
        self.assertEqual(summary['fft32768']['strict_fit_ok'],0)
        self.assertEqual(summary['fft32768']['attempts'],1)

    def test_nonfinite_curve_cannot_pass(self):
        for values,reference in (([math.nan,1.],[1.,1.]),([1.,math.inf],[1.,1.]),
                                  ([1.,1.],[math.nan,1.]),([1.,1.],[0.,0.])):
            with self.assertRaises(ValueError):
                b.curve_error(values,reference)
        self.assertAlmostEqual(b.curve_error([1.,2.],[1.,1.]),1.)

    def test_safe_fft_sizes(self):
        self.assertEqual(math.isqrt(2**31-1),b.MAX_SAFE_FFT_POINTS)
        self.assertTrue(all(n*n <= 2**31-1 for _,_,n,_ in b.METHODS))
        with self.assertRaises(ValueError):
            b.factory(None,{},('unsafe','fft',65536,1.),'unsafe')

    def test_timeout_not_reported_as_completed_fit_time(self):
        rows=[dict(method='adaptive5',case_id='e1:896',repeat=0,fit_wall_s=2.),
              dict(method='fft32768',case_id='e1:896',repeat=0,fit_wall_s=None,
                   outcome='timeout',fit_wall_lower_bound_s=30.)]
        s=b.summarize(rows)['fft32768']
        self.assertEqual(s['timeouts'],1)
        self.assertIsNone(s['median_fit_s'])
        self.assertIsNone(s['paired_median_speedup'])
        self.assertEqual(s['paired_timing_pairs'],0)

    def test_watchdog_kills_stuck_native_call(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d)/'worker'
            # ctypes releases the GIL inside libc sleep; the external watchdog
            # must terminate it without cooperation from a Python handler.
            code=('import ctypes,json,pathlib,sys,time; p=pathlib.Path(sys.argv[1]); '
                  'p.mkdir(); (p/"progress.json").write_text(json.dumps('
                  '{"stage":"fit","phase":"fit","monotonic_s":time.monotonic()})); '
                  'ctypes.CDLL(None).sleep(30)')
            r=runner.run_worker([sys.executable,'-c',code,str(directory)],directory,
                Path(d)/'worker.log',dict(startup=5.,fit=.2,checks=5.),10.,poll=.02)
            self.assertEqual(r['outcome'],'timeout')
            self.assertEqual(r['timeout_phase'],'fit')
            self.assertLess(r['worker_wall_s'],5.)
            if os.name=='posix':
                with self.assertRaises(ProcessLookupError): os.kill(r['worker_pid'],0)
            # A timeout must not poison the next task.
            r=runner.run_worker([sys.executable,'-c','print("next")'],Path(d)/'next',
                Path(d)/'next.log',dict(startup=5.,fit=.2,checks=5.),10.,poll=.02)
            self.assertEqual(r['outcome'],'completed')

    def test_watchdog_classifies_crash(self):
        with tempfile.TemporaryDirectory() as d:
            r=runner.run_worker([sys.executable,'-c','raise SystemExit(7)'],Path(d)/'worker',
                Path(d)/'worker.log',dict(startup=5.,fit=5.,checks=5.),10.,poll=.02)
            self.assertEqual(r['outcome'],'crash')
            self.assertEqual(r['worker_returncode'],7)

    def test_checkpoint_preserves_fit(self):
        with tempfile.TemporaryDirectory() as d:
            old=b.PROGRESS_PATH
            try:
                b.PROGRESS_PATH=Path(d)/'progress.json'
                b.progress('fit returned',row={'status':4000,'fit_wall_s':.3})
                b.progress('reference peak/FWHM')
                self.assertEqual(runner.read_json(Path(d)/'partial-fit.json')['fit_wall_s'],.3)
            finally:
                b.PROGRESS_PATH=old


if __name__=='__main__': unittest.main()
