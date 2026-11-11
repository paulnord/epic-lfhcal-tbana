"""Native ROOT RF summary regressions; numeric tests do not require PyROOT."""
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('root_rf_summary',Path(__file__).with_name('root_rf_summary.py'))
rf=importlib.util.module_from_spec(spec);spec.loader.exec_module(rf)
try:
    import ROOT
except ImportError:
    ROOT=None


def fixture(run=300,code=1):
    rows={run:[{'cell':c,'status':0,'amplitude':float(i+1),'fwhm':float(i+2),'peak_time':float(i)-47.5} for i,c in enumerate(rf.CELLS)]}
    settings={run:{'RF':str(code),'CF':'7','CC':'5','CFComp':'1'}}
    return rows,settings


class NumericTests(unittest.TestCase):
    def test_mean_median_and_all_64_cells(self):
        rows,settings=fixture();s=rf.summarize(rows,settings)
        self.assertEqual(s['runs'][0]['resistance_kOhm'],80)
        self.assertEqual(s['runs'][0]['metrics']['amplitude']['mean'],32.5)
        self.assertEqual(s['runs'][0]['metrics']['amplitude']['median'],32.5)
        self.assertEqual(s['finite_totals'],{'amplitude':64,'fwhm':64,'peak_time':64})

    def test_invalid_width_retains_extreme_amplitude_negative_time(self):
        rows,settings=fixture();rows[300][0].update(status=7,amplitude=1303.25,fwhm=None,peak_time=-200.5)
        s=rf.summarize(rows,settings)['runs'][0]
        self.assertEqual(s['metrics']['amplitude']['n'],64);self.assertEqual(s['metrics']['amplitude']['max'],1303.25)
        self.assertEqual(s['metrics']['peak_time']['min'],-200.5)
        self.assertEqual(s['metrics']['fwhm']['n'],63);self.assertEqual(s['metrics']['fwhm']['unavailable'],1)
        self.assertEqual(s['status_counts'],{'0':63,'7':1})

    def test_missing_nonfinite_not_zero(self):
        rows,settings=fixture()
        for r in rows[300]:r['fwhm']=None
        rows[300][0]['amplitude']=math.inf;rows[300][1]['amplitude']=math.nan
        s=rf.summarize(rows,settings)['runs'][0]
        self.assertEqual(s['metrics']['amplitude']['n'],62)
        self.assertIsNone(s['metrics']['fwhm']['mean']);self.assertIsNone(s['metrics']['fwhm']['median'])
        json.dumps(s,allow_nan=False)

    def test_dynamic_run302_with_legacy_groups(self):
        rows,settings=fixture();extra,extra_settings=fixture(302,2);rows.update(extra);settings.update(extra_settings)
        result=rf.summarize(rows,settings,[('RF',[300])])
        self.assertEqual([(s['run'],s['resistance_kOhm']) for s in result['runs']],[(302,40),(300,80)])

    def test_unrelated_settings_not_in_rf_family(self):
        rows,settings=fixture();extra,es=fixture(353,9);rows.update(extra);settings.update(es);settings[353]['CC']='1'
        self.assertEqual(rf.select_runs(rows,settings),[300])
        with self.assertRaisesRegex(ValueError,'fixed CF7'):rf.select_runs(rows,settings,[('RF',[300,353])])

    def test_zero_rf_rejected(self):
        rows,settings=fixture(code=0)
        with self.assertRaisesRegex(ValueError,'RF code'):rf.summarize(rows,settings)

    def test_duplicate_or_missing_cells_rejected(self):
        rows,settings=fixture();rows[300][1]['cell']=rows[300][0]['cell']
        with self.assertRaisesRegex(ValueError,'64 Ari cells'):rf.summarize(rows,settings)

    def test_input_unchanged(self):
        rows,settings=fixture();before=json.dumps([rows,settings],sort_keys=True)
        rf.summarize(rows,settings)
        self.assertEqual(json.dumps([rows,settings],sort_keys=True),before)

    def test_full_value_range_keeps_extremes(self):
        lo,hi=rf.value_range([-200,2,1303]);self.assertLess(lo,-200);self.assertGreater(hi,1303)


@unittest.skipIf(ROOT is None,'PyROOT unavailable; native rendering checks not run')
class NativeROOTTests(unittest.TestCase):
    def test_native_graphs_and_dynamic_x(self):
        rows,settings=fixture();rr,ss=fixture(302,2);rows.update(rr);settings.update(ss)
        rows[300][0].update(status=7,amplitude=1303.25,fwhm=None,peak_time=-200.5)
        with tempfile.TemporaryDirectory() as d:
            result=rf.draw(ROOT,rows,settings,Path(d),[('RF',[300])])
            for name in ['HGCROC_RFResistance.root','HGCROC_RFResistance.pdf','HGCROC_RFResistance.png','HGCROC_RFResistance_channels.png','HGCROC_RFResistance_audit.png','HGCROC_RFResistance_summary.json']:
                self.assertGreater((Path(d)/name).stat().st_size,100)
            f=ROOT.TFile.Open(str(Path(d)/'HGCROC_RFResistance.root'))
            try:
                for key,_ in rf.METRICS:
                    g=f.Get('rf_mean_'+key);self.assertEqual(g.ClassName(),'TGraph');self.assertEqual(g.GetN(),2)
                    self.assertEqual([g.GetPointX(i) for i in range(g.GetN())],[40,80])
                self.assertEqual(f.Get('rf_channels_amplitude').GetN(),128)
                self.assertEqual(f.Get('rf_channels_fwhm').GetN(),127)
                self.assertEqual(f.Get('rf_missing_width_channels_amplitude').GetN(),1)
                for name in ['rf_resistance_summary','rf_resistance_channels','rf_resistance_audit']:self.assertTrue(f.Get(name).InheritsFrom('TCanvas'))
                self.assertEqual(json.loads(str(f.Get('rf_resistance_summary_json').GetString()))['finite_totals'],result['finite_totals'])
                for p in result['panels']:
                    if p['page']==2:self.assertEqual(p['clipped_finite_values'],0)
            finally:f.Close()


if __name__=='__main__':unittest.main()
