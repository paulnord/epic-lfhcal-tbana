#!/usr/bin/env python3
"""Fast tests of input setup/reporting; ROOT smoke tests use --self-test."""
import csv
import math
from pathlib import Path
import tempfile
import unittest
import benchmark as b


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

    def test_paired_timing(self):
        rows=[dict(method='adaptive5',case_id='e1:903',repeat=0,fit_wall_s=4.,status=0),
              dict(method='fft65536',case_id='e1:903',repeat=0,fit_wall_s=2.,status=1)]
        summary=b.summarize(rows)
        self.assertEqual(summary['fft65536']['paired_median_speedup'],2.)
        self.assertEqual(summary['fft65536']['strict_fit_ok'],0)
        self.assertEqual(summary['fft65536']['attempts'],1)


if __name__=='__main__': unittest.main()
