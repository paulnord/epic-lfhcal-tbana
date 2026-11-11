"""Plot-only integration contracts; no detector events or scheduler calls."""
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent

def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

plots=module('plot_all_scans')
prepare=module('prepare_all_scans')
try:
    from yall_run.model import load_spec
except ImportError:
    load_spec=None

class InventoryTests(unittest.TestCase):
    def test_legacy_groups_unchanged(self):
        self.assertEqual(plots.scan_groups(plots.EXPECTED),plots.GROUPS)
    def test_rf2_inserted_at_true_code_order(self):
        groups=plots.scan_groups([*plots.EXPECTED,302])
        self.assertEqual(groups[0][1][-3:],[304,302,300])
        self.assertEqual(groups[1:],plots.GROUPS[1:])
    def test_unknown_or_missing_run_fails(self):
        for runs in ([*plots.EXPECTED,999],[r for r in plots.EXPECTED if r!=300]):
            with self.assertRaises(ValueError):plots.scan_groups(runs)
    def test_optional_only_if_existing_or_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);rf=base/'rf';other=base/'other'
            self.assertNotIn(302,plots.input_paths(rf,other))
            path=rf/'products/waveform/calibratedHGCROC_wave_Run_302_Hists.root'
            path.parent.mkdir(parents=True);path.touch()
            self.assertEqual(plots.input_paths(rf,other)[302],path)
            external=base/'external302.root'
            self.assertEqual(plots.input_paths(rf,other,external)[302],external)

class CSVTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'measurements.csv'
        self.settings=plots.read_settings(prepare.REPO/'configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv')
        self.records=[]
        for run in [*plots.EXPECTED,302]:
            for i,cell in enumerate(plots.CELLS):
                status=6 if i==0 else 0
                self.records.append(dict(run=run,**{k:self.settings[run][k] for k in ('RF','CF','CC','CFComp')},cell=cell,status=status,amplitude=100.125+i,fwhm='' if i==0 else 2,peak_time=-49.5+i))
    def write(self):
        with self.path.open('w',newline='') as stream:
            w=csv.DictWriter(stream,fieldnames=list(self.records[0]));w.writeheader();w.writerows(self.records)
    def test_exact_floats_narrow_width_negative_time_and_missing_preserved(self):
        self.write();rows=plots.read_csv_measurements(self.path,self.settings)
        self.assertEqual(len(rows),23)
        self.assertEqual(rows[302][0],dict(cell=1152,status=6,amplitude=100.125,fwhm=None,peak_time=-49.5))
        self.assertEqual(rows[300][1]['fwhm'],2.)
    def test_duplicate_cell_rejected(self):
        self.records[1]=dict(self.records[0]);self.write()
        with self.assertRaisesRegex(ValueError,'one row'):plots.read_csv_measurements(self.path,self.settings)
    def test_status_missing_disagreement_rejected(self):
        self.records[0]['fwhm']=0;self.write()
        with self.assertRaisesRegex(ValueError,'status/value'):plots.read_csv_measurements(self.path,self.settings)
    def test_nonfinite_value_rejected(self):
        self.records[0]['amplitude']='nan';self.write()
        with self.assertRaisesRegex(ValueError,'Invalid saved'):plots.read_csv_measurements(self.path,self.settings)
    def test_settings_mismatch_rejected(self):
        self.records[0]['RF']=2;self.write()
        with self.assertRaisesRegex(ValueError,'settings differ'):plots.read_csv_measurements(self.path,self.settings)

@unittest.skipIf(load_spec is None,'yall-run unavailable; actual preparation graph not tested')
class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='root-plots-');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.rf=self.base/'rf';self.other=self.base/'other'
        self.eic=self.base/'eic-shell';self.eic.write_text('#!/bin/sh\n');self.eic.chmod(0o755)
        for path in plots.input_paths(self.rf,self.other).values():
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic-path-only')
    def generate(self,**kw):
        dest=self.base/'out'
        with contextlib.redirect_stdout(io.StringIO()):prepare.prepare(dest,self.rf,self.other,self.eic,**kw)
        return load_spec(dest/'Yallfile'),json.loads((dest/'preparation.json').read_text())
    def test_legacy_graph(self):
        spec,metadata=self.generate()
        self.assertEqual(len(spec.tasks),1);self.assertEqual(len(spec.tasks[0].inputs),25)
        self.assertEqual(len(metadata['inputs']),22)
    def test_native_diagnostics_graph(self):
        spec,metadata=self.generate(rf_diagnostics=True)
        self.assertEqual(len(spec.tasks[0].inputs),28)
        self.assertTrue(metadata['rf_diagnostics'])
        self.assertIn('root_rf_channels.py',str(spec));self.assertIn('--rf-diagnostics',str(spec))
    def test_external302_graph(self):
        external=self.base/'analyzed302.root';external.write_bytes(b'existing-not-reprocessed')
        spec,metadata=self.generate(run302=external)
        self.assertEqual(len(spec.tasks[0].inputs),26)
        self.assertEqual(metadata['inputs'][-1]['run'],302)
        self.assertEqual(metadata['inputs'][-1]['path'],str(external))
    def test_missing_explicit302_fails_without_output(self):
        with self.assertRaisesRegex(ValueError,'Missing/empty'):
            self.generate(run302=self.base/'absent302.root')
        self.assertFalse((self.base/'out').exists())

if __name__=='__main__':unittest.main()
