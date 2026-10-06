#!/usr/bin/env python3
"""Offline integration tests: python3 -m unittest -v test_download_calibration_raw."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zlib

SCRIPT = Path(__file__).with_name('download_calibration_raw.py')
spec = importlib.util.spec_from_file_location('raw_downloader', SCRIPT)
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)

FAKE_CLIENT = r'''#!/usr/bin/env python3
import json, os, sys, zlib
from pathlib import Path
from urllib.parse import urlsplit

args = sys.argv[1:]
root = Path(os.environ['FAKE_REMOTE'])
if Path(sys.argv[0]).name == 'xrdfs':
    path = args[-1]
else:
    path = urlsplit(args[-2]).path
campaign = 'ps' if '2026_PST10' in path else 'sps'
source = root / campaign / Path(path).name
if not source.exists():
    sys.stderr.write('No such file: ' + str(source)); sys.exit(54)
data = source.read_bytes()
if Path(sys.argv[0]).name == 'xrdfs':
    if args[1] == 'stat':
        print('Path: ' + path + '\nSize: ' + str(len(data)))
    elif args[1:3] == ['query', 'checksum']:
        print('adler32 %08x' % (zlib.adler32(data) & 0xffffffff))
    else:
        sys.exit(2)
else:
    with open(os.environ['FAKE_COPY_LOG'], 'a') as log:
        log.write(json.dumps(args) + '\n')
    target = Path(args[-1])
    sentinel = root / 'failed-once'
    if os.environ.get('FAKE_FAIL_ONCE') and not sentinel.exists():
        target.write_bytes(data[:len(data)//2]); sentinel.touch(); sys.exit(1)
    if target.exists():
        if '--continue' not in args:
            sys.exit(17)
        offset = target.stat().st_size
        with target.open('ab') as handle:
            handle.write(data[offset:])
    else:
        target.write_bytes(data)
'''


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'downloads'
        self.remote = self.root / 'remote'
        self.log = self.root / 'copies.jsonl'
        bin_dir = self.root / 'bin'; bin_dir.mkdir()
        for command in ('xrdfs', 'xrdcp'):
            client = bin_dir / command
            client.write_text(FAKE_CLIENT)
            client.chmod(0o755)
        self.env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                        FAKE_REMOTE=str(self.remote), FAKE_COPY_LOG=str(self.log))
        self.entries = downloader.make_plan(['ps-i2'], self.out, downloader.REMOTE_ROOTS)
        self.populate(self.entries)

    def populate(self, entries):
        for entry in entries:
            path = self.remote / entry['campaign'] / entry['filename']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((entry['campaign'] + ':' + str(entry['run']) + '\n').encode() * 128)

    def run_cli(self, *args, expected=0, sets='ps-i2'):
        result = subprocess.run([sys.executable, str(SCRIPT), '--out', str(self.out),
                                 '--sets', sets, '--jobs', '1', *args], env=self.env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
        self.assertEqual(result.returncode, expected, result.stdout)
        return result.stdout

    def copies(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_catalog_scope_deduplication_and_campaign_isolation(self):
        all_files = downloader.make_plan(downloader.expand_sets(['all']), self.out, downloader.REMOTE_ROOTS)
        self.assertEqual(len(all_files), 151)
        self.assertEqual(sum(e['campaign'] == 'ps' for e in all_files), 92)
        self.assertEqual(sum(e['campaign'] == 'sps' for e in all_files), 59)
        reused = downloader.make_plan(['ps-h1', 'ps-i1', 'ps-b1', 'ps-b2'], self.out, downloader.REMOTE_ROOTS)
        self.assertEqual(len(reused), 15)
        self.assertEqual(len(next(e for e in reused if e['run'] == 215)['used_by']), 2)
        overlapping = [e for e in all_files if e['run'] == 339]
        self.assertEqual(len({e['local_path'] for e in overlapping}), 2)
        self.assertEqual(sum(len(c.get('pedestal_muon_pairs', [])) for c in downloader.CATALOG.values()), 28)

    def test_default_is_offline_plan(self):
        output = self.run_cli()
        self.assertIn('Offline plan only', output)
        self.assertEqual(self.copies(), [])
        self.assertFalse((self.out / 'ps-2026' / 'raw').exists())
        manifest = next((self.out / 'manifests').glob('*/ps-i2.json'))
        self.assertEqual(json.loads(manifest.read_text())['pedestal_runs'], [462])

    def test_remote_check_does_not_download(self):
        output = self.run_cli('--check')
        self.assertIn('Remote preflight complete', output)
        self.assertEqual(self.copies(), [])
        self.assertFalse((self.out / 'ps-2026' / 'raw').exists())

    def test_missing_remote_stops_all_transfers(self):
        (self.remote / 'ps' / 'Run463.h2g').unlink()
        self.assertIn('No raw transfers started', self.run_cli('--download', expected=1))
        self.assertEqual(self.copies(), [])

    def test_download_resume_verify_then_skip(self):
        self.env['FAKE_FAIL_ONCE'] = '1'
        output = self.run_cli('--download')
        self.assertIn('(resume)', output)
        self.assertEqual(len(self.copies()), 4)
        self.assertIn('--continue', self.copies()[1])
        for entry in self.entries:
            path = Path(entry['local_path'])
            self.assertEqual(path.read_bytes(), (self.remote / 'ps' / entry['filename']).read_bytes())
            self.assertFalse(path.with_name(path.name + '.part').exists())
            self.assertTrue(path.with_name(path.name + '.verified.json').exists())
        self.assertIn('OK existing', self.run_cli('--download'))
        self.assertEqual(len(self.copies()), 4)
        self.assertIn('VERIFY existing', self.run_cli('--download', '--recheck'))
        self.assertEqual(len(self.copies()), 4)

    def test_adopt_existing_and_preserve_corruption(self):
        entry = self.entries[0]
        path = Path(entry['local_path']); path.parent.mkdir(parents=True)
        good = (self.remote / 'ps' / entry['filename']).read_bytes()
        path.write_bytes(good)
        self.assertIn('VERIFY existing', self.run_cli('--download'))
        self.assertEqual(len(self.copies()), 2)
        path.write_bytes(b'x' * len(good))
        self.assertIn('Size/checksum mismatch', self.run_cli('--download', expected=1))
        self.assertEqual(path.read_bytes(), b'x' * len(good))
        self.assertEqual(len(self.copies()), 2)

    def test_changed_source_invalidates_receipt(self):
        self.run_cli('--download')
        source = self.remote / 'ps' / self.entries[0]['filename']
        source.write_bytes(b'z' * source.stat().st_size)
        self.assertIn('Size/checksum mismatch', self.run_cli('--download', expected=1))
        self.assertEqual(len(self.copies()), 3)

    def test_untracked_partial_is_not_resumed(self):
        path = Path(self.entries[0]['local_path'])
        path.parent.mkdir(parents=True)
        partial = path.with_name(path.name + '.part'); partial.write_bytes(b'unknown')
        self.assertIn('Untracked or changed-source partial', self.run_cli('--download', expected=1))
        self.assertEqual(partial.read_bytes(), b'unknown')
        self.assertFalse(path.exists())
        self.assertEqual(len(self.copies()), 2)

    def test_complete_corrupt_partial_is_not_published(self):
        entry = self.entries[0]
        path = Path(entry['local_path']); path.parent.mkdir(parents=True)
        data = (self.remote / 'ps' / entry['filename']).read_bytes()
        partial = path.with_name(path.name + '.part'); partial.write_bytes(b'x' * len(data))
        partial.with_name(path.name + '.part.json').write_text(json.dumps(dict(
            url=entry['url'], size=len(data), adler32='%08x' % (zlib.adler32(data) & 0xffffffff))))
        self.assertIn('Size/checksum mismatch', self.run_cli('--download', expected=1))
        self.assertFalse(path.exists())
        self.assertEqual(partial.read_bytes(), b'x' * len(data))

    def test_ps_and_sps_same_run_number_are_separate_files(self):
        entries = downloader.make_plan(['ps-f1', 'sps-param3'], self.out, downloader.REMOTE_ROOTS)
        self.populate(entries)
        self.run_cli('--download', sets='ps-f1,sps-param3')
        ps = (self.out / 'ps-2026/raw/Run339.h2g').read_bytes()
        sps = (self.out / 'sps-2026/raw/Run339.h2g').read_bytes()
        self.assertNotEqual(ps, sps)


if __name__ == '__main__':
    unittest.main()
