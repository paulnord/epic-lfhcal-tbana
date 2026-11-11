"""Math, provenance, dynamic RF2 and native ROOT object regressions."""
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('root_rf_channels', HERE/'root_rf_channels.py')
channels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(channels)
MAP = HERE.parents[2]/'configs/TB2026/mapping_HGCROC_SPSH2TB_sumV2_default.csv'
CELLS = [base+i for base in (1152,1216,1408,1472,1536,1600,1792,1856) for i in range(8)]
try:
    import ROOT
except ImportError:
    ROOT = None


def fixture(include_rf2=False):
    settings = {run:dict(RF=str(code), CF='7', CC='5', CFComp='1')
                for run, code in [(300,1),(304,3),(298,9)] + ([(302,2)] if include_rf2 else [])}
    rows = {}
    for run in settings:
        rows[run] = [dict(cell=cell, status=0, amplitude=float(100+i+(300-run)),
                          fwhm=float(50+i), peak_time=float(-10+i)) for i,cell in enumerate(CELLS)]
    rows[300][0]['fwhm'] = 2.
    rows[300][9].update(status=6, fwhm=None, amplitude=1234., peak_time=-47.5)
    rows[300][31].update(status=7, fwhm=None)
    return rows, settings


class NumericalTests(unittest.TestCase):
    def test_average_tied_ranks(self):
        self.assertEqual(channels.average_ranks([5,1,1,9]), [3,1.5,1.5,4])

    def test_correlations_and_undefined(self):
        self.assertAlmostEqual(channels.pearson([1,2,3],[6,4,2]), -1.)
        self.assertIsNone(channels.pearson([1,1],[2,3]))
        self.assertIsNone(channels.pearson([],[]))
        with self.assertRaises(ValueError):channels.pearson([1],[1,2])

    def test_pairs_use_ids_not_row_order(self):
        rows,settings=fixture()
        other=list(reversed(rows[304]))
        p=channels.paired_values(rows[300],other,'amplitude')
        self.assertEqual(len(p),64)
        self.assertEqual(p[0],(1152,96.,100.))
        self.assertEqual(channels.pair_statistics(rows[300],other,'fwhm')['n'],62)
        self.assertEqual(channels.pair_statistics(rows[300],other,'peak_time')['n'],64)
        self.assertIn((1217,105.,1234.),p)

    def test_pairs_reject_missing_or_duplicate_cells(self):
        rows,_=fixture()
        with self.assertRaisesRegex(ValueError,'identical'):channels.paired_values(rows[300],rows[304][:-1],'fwhm')
        with self.assertRaisesRegex(ValueError,'Duplicate'):channels.index_rows(rows[300]+rows[300][:1])

    def test_rf2_optional_dynamic(self):
        rows,settings=fixture()
        self.assertEqual(channels.select_rf_runs(rows,settings),[300,304,298])
        rows,settings=fixture(True)
        self.assertEqual(channels.select_rf_runs(rows,settings),[300,302,304,298])
        self.assertEqual(channels.select_rf_runs(rows,settings,[('RF',[298,300,302,304])]),[300,302,304,298])

    def test_group_rejects_fixed_setting_changes(self):
        rows,settings=fixture();settings[304]['CC']='8'
        with self.assertRaisesRegex(ValueError,'fixed setting'):
            channels.select_rf_runs(rows,settings,[('RF',[300,304,298])])

    def test_nominal_geometry_verified(self):
        g=channels.load_geometry(MAP,CELLS)
        self.assertEqual(len(g),64)
        self.assertEqual((g[1408]['asic'],g[1408]['module'],g[1408]['xbin'],g[1408]['ybin']), (1,2,1,16))
        self.assertEqual((g[1859]['asic'],g[1859]['channel'],g[1859]['half'],g[1859]['xbin'],g[1859]['ybin']), (5,2,0,4,10))
        self.assertEqual(len({(v['xbin'],v['ybin']) for v in g.values()}),64)

    def test_unknown_mapping_fails_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'map.txt';path.write_text(MAP.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'Unverified nominal geometry'):
                channels.load_geometry(path,CELLS)


@unittest.skipIf(ROOT is None,'PyROOT unavailable; native ROOT rendering/object tests not run')
class NativeROOTTests(unittest.TestCase):
    def test_native_objects_preserve_failed_width_and_finite_peak(self):
        rows,settings=fixture(True)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            result=channels.draw(ROOT,rows,settings,out,MAP)
            self.assertEqual(result['rf_runs'],[300,302,304,298])
            self.assertEqual(result['page_count'],5)
            self.assertEqual(result['correlations']['304']['fwhm']['n'],62)
            self.assertEqual(result['correlations']['304']['amplitude']['n'],64)
            self.assertTrue((out/'HGCROC_RFChannels.pdf').read_bytes().startswith(b'%PDF'))
            self.assertEqual(len(list(out.glob('HGCROC_RFChannels_*.png'))),5)
            f=ROOT.TFile.Open(str(out/'HGCROC_RFChannels.root'),'READ')
            try:
                for name in ['rf_channels_amplitude','rf_channels_fwhm','rf_channels_status','rf_channels_pairs','rf_channels_correlations']:
                    self.assertTrue(f.Get(name).InheritsFrom('TCanvas'))
                canvas=f.Get('rf_channels_amplitude')
                pad=canvas.GetListOfPrimitives().FindObject('pad_amplitude_300')
                self.assertTrue(pad.GetListOfPrimitives().FindObject('palette_amplitude_300').InheritsFrom('TExec'))
                canvas.Draw();canvas.cd();canvas.Modified();canvas.Update()
                self.assertTrue(f.Get('map_run300_amplitude').InheritsFrom('TH2D'))
                self.assertTrue(f.Get('map_run300_status').InheritsFrom('TH2I'))
                geo=channels.load_geometry(MAP,CELLS)[1217]
                x,y=geo['xbin'],geo['ybin']
                self.assertTrue(math.isnan(f.Get('map_run300_fwhm').GetBinContent(x,y)))
                self.assertEqual(f.Get('finite_mask_run300_fwhm').GetBinContent(x,y),0)
                self.assertEqual(f.Get('status_map_run300_fwhm').GetBinContent(x,y),6)
                self.assertEqual(f.Get('map_run300_amplitude').GetBinContent(x,y),1234.)
                self.assertEqual(f.Get('values_run300_amplitude').GetN(),64)
                self.assertEqual(f.Get('values_run300_fwhm').GetN(),62)
                self.assertEqual(f.Get('values_run302_amplitude').GetN(),64)
                self.assertEqual(f.Get('paired_run300_run304_fwhm').GetN(),62)
                self.assertEqual(f.Get('paired_run300_run304_amplitude').GetN(),64)
                self.assertEqual(f.Get('paired_run300_run304_fwhm_narrow').GetN(),1)
                saved=json.loads(str(f.Get('rf_channel_metadata_json').GetString()))
                self.assertEqual(saved['mapping_sha256'],channels.VERIFIED_MAPPING_SHA256)
                self.assertIn('302',saved['correlations'])
            finally:f.Close()


if __name__=='__main__':unittest.main()
