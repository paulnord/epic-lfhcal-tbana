"""ROOT-free tests of workflow construction; not production ROOT validation."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import adaptive_fulltests as f

class FullChainTests(unittest.TestCase):
    def test_known_e3_toa_and_runs(self):
        self.assertEqual(f.SPECS['e3']['toa'],'F')
        self.assertEqual(f.SPECS['e3']['muons'],[473,474,477,478,481,482])
        self.assertEqual(f.SPECS['b2']['pedestal'],126)
    def test_51_node_dag_and_build_gate(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);f.dump(out/'manifest.json',{'eic_shell':'/eic-shell'})
            text=f.yallfile(out)
        lines=text.splitlines()
        tasks={s.split(':',1)[0]:s.split(':',1)[1].split()
               for s in lines if s and not s[0].isspace() and ':' in s}
        self.assertEqual(len(tasks),51)
        for name,deps in tasks.items():
            for dep in deps:self.assertIn(dep,tasks)
        self.assertEqual(tasks['input-e3'],['build-legacy','build-adaptive'])
        for m in f.MODELS:
            self.assertEqual(tasks[f'mip-{m}-b2'],['input-b2'])
            self.assertEqual(tasks[f'refine1-{m}-b2'],[f'select-{m}-b2'])
            self.assertEqual(tasks[f'refine5-{m}-b2'],[f'refine4-{m}-b2'])
        self.assertEqual(tasks['compare-e1'],['refine5-legacy-e1','refine5-adaptive-e1'])
    def test_initial_pass_uses_common_pre_mip_file(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);p=out/'common.root';p.write_text('x')
            f.dump(out/'inputs/b2/ready.json',{'transfer':f.file_info(p)})
            for m in f.MODELS:
                cmd=list(map(str,f.stage_command(out,m,'b2','mip','DataPrep')))
                self.assertEqual(cmd[cmd.index('-i')+1],str(p))
                self.assertIn('-s',cmd);self.assertNotIn('-S',cmd)
                self.assertNotIn('-L',cmd)
    def test_refinements_use_own_skim_and_previous_calibration(self):
        out=Path('/test')
        for m in f.MODELS:
            for n in range(1,6):
                cmd=list(map(str,f.stage_command(out,m,'e1',f'refine{n}','DataPrep')))
                self.assertIn('-S',cmd);self.assertIn('-x',cmd);self.assertNotIn('-L',cmd)
                self.assertEqual(cmd[cmd.index('-i')+1],str(f.paths(out,m,'e1','select')['root']))
                if n==1:self.assertNotIn('-k',cmd)
                else:self.assertEqual(cmd[cmd.index('-k')+1],str(f.paths(out,m,'e1',f'refine{n-1}')['calib']))
    def test_event_skim_flag_is_X_not_M(self):
        cmd=f.stage_command(Path('/test'),'adaptive','e3','select','DataPrep')
        self.assertIn('-X',cmd);self.assertNotIn('-M',cmd)
    def test_output_trees_are_disjoint(self):
        out=Path('/test');all_paths=[]
        for m in f.MODELS:
            for c in f.SPECS:
                for s in f.STAGES:all_paths.append(str(f.paths(out,m,c,s)['root']))
        self.assertEqual(len(all_paths),len(set(all_paths)))
    def test_input_prefers_existing_pre_mip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);transfer=root/'fullset-e1-repro/transfer/rawHGCROC_wPed_wBC_Muon_FullSetE_1.root'
            transfer.parent.mkdir(parents=True);transfer.write_text('root')
            found=f.find_inputs('e1',root,root/'archive',root/'raw')
            self.assertEqual(found['mode'],'transfer')
            self.assertEqual(found['files']['transfer']['path'],str(transfer))
    def test_never_substitutes_selected_for_missing_initial_input(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'adaptive-fullset-e1-repro/selected/fake.root'
            p.parent.mkdir(parents=True);p.write_text('selected')
            with self.assertRaisesRegex(ValueError,'no pre-MIP'):
                f.find_inputs('e1',root,root/'archive',root/'raw')
    def test_raw_fallback_requires_every_listed_run(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/'raw';raw.mkdir()
            runs=[f.SPECS['e3']['pedestal']]+f.SPECS['e3']['muons']
            for r in runs:(raw/f'Run{r}.h2g').write_text('raw')
            self.assertEqual(f.find_inputs('e3',root,root/'archive',raw)['mode'],'raw')
            (raw/'Run482.h2g').unlink()
            with self.assertRaises(ValueError):f.find_inputs('e3',root,root/'archive',raw)
    def test_input_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input';p.write_text('x');info=f.file_info(p)
            p.write_text('changed')
            with self.assertRaises(ValueError):f.check_info(info)
    def test_native_timeout_records_failure(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'native.log'
            with self.assertRaisesRegex(RuntimeError,'timeout'):
                f.run([sys.executable,'-c','import ctypes; ctypes.CDLL(None).sleep(20)'],Path(d),log,.15)
            self.assertEqual(f.load(str(log)+'.json')['outcome'],'timeout')
    def test_subprocess_failure_records_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'failure.log'
            with self.assertRaises(RuntimeError):
                f.run([sys.executable,'-c','raise SystemExit(7)'],Path(d),log,2)
            self.assertEqual(f.load(str(log)+'.json')['returncode'],7)
    def test_calibration_sentinels_duplicates_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'calib.txt'
            line='1 0 0 0 0 80 1 80 1 -1000 -1000 -1000 -1000 -64 -1000 -64 -1000 3\n'
            p.write_text(line);self.assertIsNone(f.calibrations(p)[1]['scale_h'])
            p.write_text(line+line)
            with self.assertRaises(ValueError):f.calibrations(p)
            p.write_text(line.replace('-1000','nan',1))
            with self.assertRaises(ValueError):f.calibrations(p)
    def test_csv_keeps_missing_values(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.csv';f.write_csv(p,[{'a':None,'b':0,'c':False}])
            with p.open() as s:r=next(csv.DictReader(s))
            self.assertEqual(r,{'a':'?','b':'0','c':'False'})
    def test_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);s=out/'sources/legacy';s.mkdir(parents=True)
            (s/'x.cc').write_text('old')
            f.dump(out/'source-hashes.json',{'legacy':f.tree_hashes(s)})
            (s/'x.cc').write_text('new')
            with self.assertRaises(ValueError):f.check_sources(out,'legacy')

if __name__=='__main__':unittest.main()
