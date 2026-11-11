"""Offline contract tests: synthetic inputs and fake EIC/CMake, never BNL/ROOT."""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('run_ari_books_local.sh').resolve()
RUNS = [298, 300, 302, 304, 306, 310, 329, 333, 335, 337, 339, 341, 343, 345,
        347, 349, 351, 353, 355, 357, 359, 361, 363]
RF = set(RUNS[:14]) - {302}
HEADER = ['run', 'cell', 'status', 'has_peak', 'has_fwhm', 'peak_bin', 'left_bin',
          'right_bin', 'amplitude', 'peak_time_ns', 'left_ns', 'right_ns', 'fwhm_ns', 'source']


class LocalBooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ari-local-test-')
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name)
        self.bin = self.p / 'bin'
        self.bin.mkdir()
        self.repo = self.p / 'repo'
        self.repo.mkdir()
        (self.repo / 'NewStructure').mkdir()
        (self.repo / 'NewStructure/CombineWaveformBooks.cc').write_text('// WaveformScale::IsolatedLayer\n')
        db = self.repo / 'configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv'
        db.parent.mkdir(parents=True)
        db.write_text('synthetic database\n')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
        self.sha = self.git('rev-parse', 'HEAD').strip()
        for run in RUNS:
            base = self.p / 'run302' if run == 302 else self.p / 'inputs' / ('rf' if run in RF else 'other')
            root = base / f'products/waveform/calibratedHGCROC_wave_Run_{run}_Hists.root'
            csvpath = base / f'products/plots/waveform/Run{run}/WaveformGrid_Run{run}_Measurements.csv'
            root.parent.mkdir(parents=True, exist_ok=True)
            csvpath.parent.mkdir(parents=True, exist_ok=True)
            root.write_bytes(b'SYNTHETIC ROOT STUB, NOT PHYSICS DATA')
            with csvpath.open('w', newline='') as f:
                w = csv.writer(f)
                w.writerow(HEADER)
                for i in range(64):
                    w.writerow([run, 1152+i, 0, 1, 1, 10, 9, 11, 100, 75, 65, 85, 20, 'synthetic'])
        self.stub('root-config', '#!/bin/bash\necho ROOT-STUB\n')
        self.stub('pdfinfo', '#!/bin/bash\necho "Pages: ${TEST_PAGES:-26}"\n')
        # Model eic-shell read without -r; optionally mask an inner failure.
        self.stub('eic-shell', '''#!/bin/bash
read line
/bin/bash -c "$line"
rc=$?
[[ ${TEST_MASK_FAILURE:-0} == 1 ]] && exit 0
exit "$rc"
''')
        self.stub('cmake', '''#!/usr/bin/env python3
import os,pathlib,sys
args=sys.argv[1:]
with open(os.environ['TEST_COMMAND_LOG'],'a') as f:f.write(repr(args)+'\\n')
if '--build' in args:
    if os.environ.get('TEST_BUILD_FAIL'):sys.exit(7)
    assert args == ['--build', args[1], '--parallel', '1', '--target', 'CombineWaveformBooks']
    p=pathlib.Path(args[1])/'CombineWaveformBooks'
    p.write_text("""#!/usr/bin/env python3
import csv,os,pathlib,sys
manifest,database,base,mode=sys.argv[1:]
assert mode in ['isolated','layer','robust','global']
rows=list(csv.DictReader(open(manifest)))
assert len(rows)==23 and sum(r['run']=='302' for r in rows)==1
for suffix in ['_Unnormalized.pdf','_Normalized.pdf']:pathlib.Path(base+suffix).write_bytes(b'%PDF-STUB')
if os.environ.get('TEST_TAMPER'):
    p=pathlib.Path(rows[0]['profile_root']);st=p.stat();p.write_bytes(b'X'*st.st_size);os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
if os.environ.get('TEST_SOURCE_TAMPER'):
    p=pathlib.Path(database);p.write_text('changed')
""")
    p.chmod(0o700)
''')
        # Any accidental scheduler use fails loudly.
        for command in ('yall-run', 'condor_submit', 'ctest'):
            self.stub(command, '#!/bin/bash\necho "UNEXPECTED SCHEDULER/TEST INVOCATION" >&2\nexit 91\n')
        self.env = os.environ.copy()
        for key in ('_CONDOR_JOB_AD', 'ARI_RF_BATCH_WORKER', 'ARI_BOOKS_LOCAL_PAYLOAD'):
            self.env.pop(key, None)
        self.env.update(PATH=str(self.bin)+os.pathsep+self.env['PATH'],
                        EIC_SHELL=str(self.bin/'eic-shell'), ARI_SOURCE_COMMIT=self.sha,
                        ARI_SOURCE_REPO=str(self.repo), ARI_INPUT_ROOT=str(self.p/'inputs'),
                        ARI_RUN302_ROOT=str(self.p/'run302'), TEST_COMMAND_LOG=str(self.p/'commands'))

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True)

    def stub(self, name, text):
        p = self.bin/name
        p.write_text(text)
        p.chmod(0o700)

    def invoke(self, **env):
        return subprocess.run(['/bin/bash', str(SCRIPT), str(self.p/'out')],
                              env={**self.env, **env}, text=True, capture_output=True, timeout=30)

    def test_success_and_no_overwrite(self):
        before = self.git('status', '--porcelain')
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
        out = self.p/'out'
        m = json.loads((out/'preparation.json').read_text())
        self.assertEqual(len(m['files']), 46)
        self.assertEqual(m['commit'], self.sha)
        self.assertTrue((out/'products/BOOKS_READY').is_file())
        self.assertTrue((out/'products/SHA256SUMS').is_file())
        self.assertEqual(before, self.git('status', '--porcelain'))
        self.assertFalse((out/'Yallfile').exists())
        commands = (self.p/'commands').read_text()
        self.assertIn("'--parallel', '1', '--target', 'CombineWaveformBooks'", commands)
        self.assertIn('-DBUILD_TESTING=OFF', commands)
        self.assertNotEqual(self.invoke().returncode, 0)

    def test_missing_run302_fails_before_destination(self):
        next((self.p/'run302').rglob('*.root')).unlink()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.p/'out').exists())

    def test_explicit_full_commit_required(self):
        self.assertNotEqual(self.invoke(ARI_SOURCE_COMMIT=self.sha[:8]).returncode, 0)
        self.assertFalse((self.p/'out').exists())

    def test_masked_build_failure_has_no_ready(self):
        self.assertNotEqual(self.invoke(TEST_BUILD_FAIL='1', TEST_MASK_FAILURE='1').returncode, 0)
        self.assertFalse((self.p/'out/products/BOOKS_READY').exists())

    def test_same_size_same_mtime_root_tamper_detected(self):
        self.assertNotEqual(self.invoke(TEST_TAMPER='1').returncode, 0)
        self.assertFalse((self.p/'out/products/BOOKS_READY').exists())

    def test_source_tamper_detected(self):
        self.assertNotEqual(self.invoke(TEST_SOURCE_TAMPER='1').returncode, 0)
        self.assertFalse((self.p/'out/products/BOOKS_READY').exists())

    def test_wrong_page_count_has_no_ready(self):
        self.assertNotEqual(self.invoke(TEST_PAGES='25').returncode, 0)
        self.assertFalse((self.p/'out/products/BOOKS_READY').exists())

    def test_batch_environment_rejected(self):
        self.assertNotEqual(self.invoke(_CONDOR_JOB_AD='job.ad').returncode, 0)
        self.assertFalse((self.p/'out').exists())

    def test_payload_cannot_be_entered_accidentally(self):
        result = subprocess.run(['/bin/bash', str(SCRIPT), '--payload', str(self.p/'out')],
                                env=self.env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
