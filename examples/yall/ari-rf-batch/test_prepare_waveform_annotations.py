#!/usr/bin/env python3
"""Annotation handoff tests using real Yall parsing; no ROOT, Condor or BNL."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yall_run.model import load_spec
from yall_run.campaign import create_campaign

HERE = Path(__file__).resolve().parent

def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

a = module('annotation_prepare', 'prepare_waveform_annotations.py')
p = module('base_prepare', 'prepare.py')

class AnnotationPreparationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='annotation-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.eic = self.base/'eic-shell'
        self.eic.write_text('#!/bin/sh\nexit 1\n')
        self.eic.chmod(0o755)
        self.destination = self.base/'annotations'
        self.campaign = self.make_campaign('original', a.RUNS)
        self.campaigns = [self.campaign]

    def make_campaign(self, label, runs):
        workspace = self.base/label
        raw = self.base/(label+'-raw')
        raw.mkdir()
        pairs = [(r-1, r, 1) for r in runs]
        for ped, run, _ in pairs:
            for n in (ped, run):
                (raw/f'Run{n}.h2g').write_bytes(b'raw-fixture')
        with contextlib.redirect_stdout(io.StringIO()):
            p.prepare(workspace, raw, self.eic, 'full', True, pairs_override=pairs,
                      campaign_name=label, include_summary=False)
            campaign = create_campaign(load_spec(workspace/'Yallfile'), self.base/'campaigns')
        manifest = a.read_json(campaign/'campaign.json')
        for name, task in manifest['tasks'].items():
            if not name.startswith('calibrate-'):
                continue
            output = next(x for x in task['outputs'] if x['role'] == 'root')
            path = Path(output['path'])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'not-ROOT-placeholder-only')
            self.finish_task(campaign, name, task, path)
        return campaign

    def finish_task(self, campaign, name, task, path):
        st = path.stat()
        state = {'state':'completed', 'attempts':1, 'last_returncode':0}
        (campaign/'state'/f'{name}.json').write_text(json.dumps(state))
        attemptdir = campaign/f'{name}_attempt_001'
        attemptdir.mkdir(exist_ok=True)
        attempt = {'task':name, 'attempt':1, 'state':'completed', 'returncode':0,
                   'command_returncode':0, 'command':task['command'],
                   'outputs':[{'role':'root', 'path':str(path), 'exists':True,
                               'size_bytes':st.st_size, 'mtime_ns':st.st_mtime_ns}]}
        (attemptdir/'attempt.json').write_text(json.dumps(attempt))

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            a.prepare(self.destination, self.campaigns, self.eic)
        return a.read_json(self.destination/'preparation.json')

    def edit(self, path, change):
        data = a.read_json(path)
        change(data)
        path.write_text(json.dumps(data))

    def test_run302_only_reuses_calibration_and_builds_two_node_graph(self):
        only = self.make_campaign('only302', (302,))
        with contextlib.redirect_stdout(io.StringIO()):
            a.prepare(self.destination, [only], self.eic, runs=(302,))
        data = a.read_json(self.destination/'preparation.json')
        self.assertEqual([x['run'] for x in data['inputs']], [302])
        tasks = {t.name:t for t in load_spec(self.destination/'Yallfile').tasks}
        self.assertEqual(set(tasks), {'build', 'waveform-302'})
        self.assertEqual(tasks['waveform-302'].parents, ('build',))

    def test_subset_still_rejects_changed_input(self):
        only = self.make_campaign('only302', (302,))
        (self.base/'only302/products/calibrated/calibratedHGCROC_Run_302.root').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Calibration changed'):
            a.prepare(self.destination, [only], self.eic, runs=(302,))
        self.assertFalse(self.destination.exists())

    def test_complete_graph_and_no_old_mutation(self):
        before = {str(f):f.read_bytes() for root in (self.base/'original', self.campaign)
                  for f in root.rglob('*') if f.is_file()}
        metadata = self.prepare()
        self.assertEqual([x['run'] for x in metadata['inputs']], list(a.RUNS))
        self.assertEqual(len(set(a.RUNS)), 23)
        self.assertIn(302, a.RUNS)
        tasks = {t.name:t for t in load_spec(self.destination/'Yallfile').tasks}
        self.assertEqual(len(tasks), 24)
        self.assertEqual(set(tasks), {'build'} | {f'waveform-{r}' for r in a.RUNS})
        for run in a.RUNS:
            self.assertEqual(tasks[f'waveform-{run}'].parents, ('build',))
        self.assertEqual(before, {name:Path(name).read_bytes() for name in before})
        self.assertEqual((self.destination/'Yallfile').read_text().count('%retry 0'), 24)

    def test_logical_source_and_campaign_paths_survive_preparation(self):
        alias = self.base/'source-alias'
        alias.symlink_to(a.REPO, target_is_directory=True)
        spec = importlib.util.spec_from_file_location('annotation_logical',
                   alias/'examples/yall/ari-rf-batch/prepare_waveform_annotations.py')
        logical = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logical)
        campaign_alias = self.base/'campaign-alias'
        campaign_alias.symlink_to(self.campaign.parent, target_is_directory=True)
        selected = campaign_alias/self.campaign.name
        with contextlib.redirect_stdout(io.StringIO()):
            logical.prepare(self.destination, [selected, self.campaign], self.eic)
        data = logical.read_json(self.destination/'preparation.json')
        self.assertEqual(data['repo'], str(alias))
        self.assertEqual({x['campaign'] for x in data['inputs']}, {str(selected)})
        self.assertTrue(all(str(selected/'campaign.json') in x['proofs'] for x in data['inputs']))
        self.assertTrue(all(path.startswith(str(alias)+'/') for path in data['code_sha256']))
        text = (self.destination/'Yallfile').read_text()
        self.assertIn(str(alias/'examples/yall/ari-rf-batch/prepare_waveform_annotations.py'), text)
        self.assertIn(str(alias/'examples/yall/ari-rf-batch/worker.sh'), text)
        self.assertNotIn(str(a.REPO), text)
        self.assertEqual(len(load_spec(self.destination/'Yallfile').tasks), 24)

    def test_worker_accepts_only_known_mount_alias_for_same_logical_file(self):
        public = '/gpfs01/star/scratch/pnord/input.root'
        internal = '/gpfs/mnt' + public
        for old, new in ((internal, public), (public, internal)):
            item = {'path':public, 'realpath':old, 'size_bytes':123, 'mtime_ns':456}
            with patch.object(a, 'record', return_value=dict(item, realpath=new)):
                a.unchanged(item)

    def test_mount_alias_does_not_hide_content_stat_changes(self):
        item = {'path':'/gpfs01/star/input.root', 'realpath':'/gpfs/mnt/gpfs01/star/input.root',
                'size_bytes':123, 'mtime_ns':456}
        for key in ('size_bytes', 'mtime_ns'):
            now = dict(item, realpath=item['path'])
            now[key] += 1
            with patch.object(a, 'record', return_value=now):
                with self.assertRaisesRegex(ValueError, key): a.unchanged(item)

    def test_mount_alias_does_not_accept_different_target(self):
        self.assertFalse(a.same_input_location('/gpfs01/star/input.root',
            '/gpfs/mnt/gpfs01/star/input.root', '/gpfs01/star/other.root'))
        self.assertFalse(a.same_input_location('/elsewhere/input.root',
            '/gpfs/mnt/gpfs01/star/input.root', '/gpfs01/star/input.root'))

    def test_input_identity_checks_still_reject_resolved_path_change(self):
        item = a.record(self.base/'original/products/calibrated/calibratedHGCROC_Run_302.root')
        changed = dict(item, realpath='/different/mount/or/target.root')
        with patch.object(a, 'record', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'realpath: recorded=.*current='):
                a.unchanged(item)

    def test_protected_destination_is_checked_through_alias(self):
        alias = self.base/'workspace-alias'
        alias.symlink_to(self.base/'original', target_is_directory=True)
        self.destination = alias/'new-annotations'
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.prepare()
        self.assertFalse(self.destination.exists())

    def test_missing_302_fails_without_destination(self):
        (self.base/'original/products/calibrated/calibratedHGCROC_Run_302.root').unlink()
        with self.assertRaisesRegex(ValueError, 'run302.*missing'):
            self.prepare()
        self.assertFalse(self.destination.exists())

    def test_failed_latest_attempt_refused(self):
        self.edit(self.campaign/'state/calibrate-301-302-1.json', lambda d:d.update(state='failed'))
        with self.assertRaisesRegex(ValueError, 'run302'):
            self.prepare()

    def test_changed_calibrated_input_refused(self):
        (self.base/'original/products/calibrated/calibratedHGCROC_Run_302.root').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Calibration changed'):
            self.prepare()

    def test_attempt_command_mismatch_refused(self):
        self.edit(self.campaign/'calibrate-301-302-1_attempt_001/attempt.json', lambda d:d.update(command=['false']))
        with self.assertRaisesRegex(ValueError, 'command differs'):
            self.prepare()

    def test_archived_hash_mismatch_refused(self):
        with (self.campaign/'Yallfile').open('a') as f:f.write('\n# changed\n')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.prepare()

    def test_added_native_force_option_refused(self):
        def mutate(d):
            task = d['tasks']['waveform-301-302-1']
            task['command'] = list(task['command']) + ['-f']
        self.edit(self.campaign/'campaign.json', mutate)
        with self.assertRaisesRegex(ValueError, 'manual review'):
            self.prepare()

    def test_ambiguous_complete_campaigns_refused(self):
        self.campaigns.append(self.make_campaign('second', a.RUNS))
        with self.assertRaisesRegex(ValueError, '[Aa]mbiguous'):
            self.prepare()

    def test_alternate_pilot_input_is_ambiguous(self):
        self.campaigns.append(self.make_campaign('pilot', [298]))
        with self.assertRaisesRegex(ValueError, '[Aa]mbiguous'):
            self.prepare()

    def test_interactive_choice_selects_explicit_complete_campaign(self):
        from unittest.mock import mock_open
        pilot = self.make_campaign('pilot', [298])
        campaigns = [self.campaign, pilot]
        ordered = sorted(campaigns)
        answer = str(ordered.index(self.campaign)+1)+'\n'
        tty = mock_open(read_data=answer)
        with patch('builtins.open', tty), contextlib.redirect_stdout(io.StringIO()):
            chosen = a.choose_campaigns(campaigns)
        self.assertEqual(chosen, [self.campaign])
        self.assertEqual(tty.call_count, 2)
        self.assertEqual([call.args for call in tty.call_args_list], [('/dev/tty', 'r'), ('/dev/tty', 'w')])
        self.assertEqual(len(a.select_inputs(chosen)), 23)
        self.assertFalse(self.destination.exists())

    @unittest.skipUnless(os.name == 'posix', 'requires a POSIX pseudo-terminal')
    def test_interactive_choice_uses_real_nonseekable_terminal(self):
        import pty
        import select
        import signal
        import sys
        import time
        pilot = self.make_campaign('pilot', [298])
        campaigns = [self.campaign, pilot]
        answer = str(sorted(campaigns).index(self.campaign)+1)+'\n'
        sys.stdout.flush()
        pid, fd = pty.fork()
        if pid == 0:
            try:
                # The launcher pipes stdout through tee, so the prompt must use
                # the controlling tty, not seek/read the output stream.
                with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink):
                    chosen = a.choose_campaigns(campaigns)
                os._exit(0 if chosen == [self.campaign] else 3)
            except BaseException as exc:
                os.write(2, (type(exc).__name__+': '+str(exc)+'\n').encode())
                os._exit(2)
        output = bytearray()
        answered = False
        status = None
        deadline = time.monotonic()+10
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([fd], [], [], .1)
                if ready:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        chunk = b''
                    if not chunk:
                        break
                    output.extend(chunk)
                    if b'Enter to stop:' in output and not answered:
                        os.write(fd, answer.encode())
                        answered = True
                waited, result = os.waitpid(pid, os.WNOHANG)
                if waited:
                    status = result
                    break
        finally:
            os.close(fd)
            if status is None:
                waited, result = os.waitpid(pid, os.WNOHANG)
                if not waited:
                    os.kill(pid, signal.SIGKILL)
                    _, result = os.waitpid(pid, 0)
                status = result
        self.assertTrue(answered, output.decode(errors='replace'))
        self.assertEqual(status, 0, output.decode(errors='replace'))
        self.assertFalse(self.destination.exists())

    def test_interactive_choice_revalidates_and_cancels_safely(self):
        from unittest.mock import mock_open
        pilot = self.make_campaign('pilot', [298])
        campaigns = [self.campaign, pilot]
        pilot_index = sorted(campaigns).index(pilot)+1
        for answer in ('\n', '1,1\n', '99\n', '1,2\n', str(pilot_index)+'\n'):
            with self.subTest(answer=answer), patch('builtins.open', mock_open(read_data=answer)), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError):a.choose_campaigns(campaigns)
            self.assertFalse(self.destination.exists())

    def test_interactive_missing_run_fails_without_prompt(self):
        from unittest.mock import mock_open
        (self.base/'original/products/calibrated/calibratedHGCROC_Run_302.root').unlink()
        tty = mock_open()
        with patch('builtins.open', tty):
            with self.assertRaisesRegex(ValueError, 'run302.*missing'):
                a.choose_campaigns(self.campaigns)
        tty.assert_not_called()

    def test_duplicate_producers_are_ambiguous(self):
        mp = self.campaign/'campaign.json'
        manifest = a.read_json(mp)
        original = manifest['tasks']['calibrate-301-302-1']
        duplicate = copy.deepcopy(original)
        manifest['tasks']['calibrate-duplicate-302'] = duplicate
        mp.write_text(json.dumps(manifest))
        path = Path(next(x['path'] for x in duplicate['outputs'] if x['role'] == 'root'))
        self.finish_task(self.campaign, 'calibrate-duplicate-302', duplicate, path)
        with self.assertRaisesRegex(ValueError, '[Mm]ultiple|[Aa]mbiguous|duplicate'):
            self.prepare()

    def test_existing_destination_refused(self):
        self.destination.mkdir()
        with self.assertRaisesRegex(ValueError, 'Destination exists'):self.prepare()

    def test_dangling_destination_symlink_refused(self):
        self.destination.symlink_to(self.base/'absent')
        with self.assertRaisesRegex(ValueError, 'Destination exists'):self.prepare()

    def test_destination_in_source_refused(self):
        self.destination = a.REPO/'annotations-test-must-not-be-created'
        with self.assertRaisesRegex(ValueError, 'outside'):self.prepare()
        self.assertFalse(self.destination.exists())

    def test_destination_in_old_workspace_refused(self):
        self.destination = self.base/'original/new-annotations'
        with self.assertRaisesRegex(ValueError, 'outside'):self.prepare()

    def test_root_substring_destination_refused(self):
        self.destination = self.base/'new.root-output'
        with self.assertRaisesRegex(ValueError, '.root'):
            self.prepare()
        self.assertFalse(self.destination.exists())

    def test_worker_rechecks_tracked_source_diff(self):
        self.prepare()
        data = a.read_json(self.destination/'preparation.json')
        with patch.dict(os.environ, {'ARI_RF_BATCH_WORKER':'1'}), \
             patch.object(a.subprocess, 'check_output', side_effect=[data['commit']+'\n', data['git_diff']+'\nchanged']):
            with self.assertRaisesRegex(ValueError, '[Ss]ource'):
                a.worker_metadata(self.destination/'preparation.json')

    def test_atomic_failure_before_publication(self):
        with patch.object(a.subprocess, 'check_output', side_effect=RuntimeError('git failed')):
            with self.assertRaises(RuntimeError):self.prepare()
        self.assertFalse(self.destination.exists())

    def test_worker_guard_requires_established_inner_marker(self):
        for env in ({}, {'ARI_RF_BATCH_WORKER':'0'}, {'_CONDOR_JOB_AD':'fixture'}):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(ValueError, 'Condor worker'):
                    a.worker_metadata(self.base/'nonexistent')

    def test_worker_rechecks_input_stats_before_root(self):
        data = self.prepare()
        Path(data['inputs'][0]['path']).write_bytes(b'changed-after-preparation')
        with patch.dict(os.environ, {'ARI_RF_BATCH_WORKER':'1', '_CONDOR_JOB_AD':'fixture'}):
            with self.assertRaisesRegex(ValueError, 'Input changed'):
                a.worker_metadata(self.destination/'preparation.json')

    def test_discovery_prunes_data_and_symlinks(self):
        root = self.base/'discovery'
        (root/'products/hidden').mkdir(parents=True)
        (root/'products/hidden/campaign.json').write_text('{}')
        (root/'visible').mkdir()
        (root/'visible/campaign.json').write_text('{}')
        (root/'alias').symlink_to(self.campaign, target_is_directory=True)
        self.assertEqual(a.discover([root]), [(root/'visible').resolve()])

    def test_discovery_preserves_supplied_root_alias(self):
        root = self.base/'discovery'
        (root/'visible').mkdir(parents=True)
        (root/'visible/campaign.json').write_text('{}')
        alias = self.base/'discovery-alias'
        alias.symlink_to(root, target_is_directory=True)
        self.assertEqual(a.discover([alias]), [alias/'visible'])

    def test_discovery_alias_dedup_keeps_first_supplied_root(self):
        root = self.base/'a-internal-storage'
        (root/'visible').mkdir(parents=True)
        (root/'visible/campaign.json').write_text('{}')
        alias = self.base/'z-worker-visible'
        alias.symlink_to(root, target_is_directory=True)
        self.assertEqual(a.discover([alias, root]), [alias/'visible'])
        self.assertEqual(a.discover([root, alias]), [root/'visible'])

    def test_discovery_directory_bound(self):
        with self.assertRaisesRegex(ValueError, 'limit'):
            a.discover([self.base], max_directories=1)

class AnnotationWorkerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='annotation-worker-test-')
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name)/'new'
        self.dest.mkdir()
        (self.dest/'build').mkdir()
        (self.dest/'build/ANNOTATIONS_READY').write_text('fixture')
        self.input = Path(self.tmp.name)/'input.root'
        self.input.write_bytes(b'fixture')
        item = a.record(self.input)
        item.update(run=302, rundb='/fixture/rundb', cells='/fixture/cells')
        self.data = {'destination':str(self.dest), 'inputs':[item]}
        self.hists = self.dest/'products/waveform/calibratedHGCROC_wave_Run_302_Hists.root'
        self.plots = self.dest/'products/plots/waveform/Run302'
        self.manifest = self.dest/'preparation.json'

    def run_worker(self, subprocess_mock):
        with patch.object(a, 'worker_metadata', return_value=self.data), \
             patch.object(a, 'verify_root'), patch.object(a.subprocess, 'run', subprocess_mock), \
             contextlib.redirect_stdout(io.StringIO()):
            a.worker_run(self.manifest, 302)

    def write_products(self, argv, **kwargs):
        self.hists.write_bytes(b'histogram-fixture')
        self.plots.mkdir(parents=True)
        for suffix in ('Original.pdf', 'Annotated.pdf', 'Measurements.csv'):
            (self.plots/f'WaveformGrid_Run302_{suffix}').write_bytes(b'report-fixture')
        self.argv = argv

    def test_retains_native_options_and_checks_products(self):
        self.run_worker(self.write_products)
        self.assertEqual(self.argv[1:], ['-d','1','-E','1','-w','-i',str(self.input),
            '-o', str(self.dest/'products/waveform/calibratedHGCROC_wave_Run_302.root'),
            '-O', str(self.plots), '-r','/fixture/rundb','-l','/fixture/cells'])

    def test_existing_histogram_refuses_execution(self):
        self.hists.parent.mkdir(parents=True)
        self.hists.write_bytes(b'old-output')
        from unittest.mock import Mock
        command = Mock()
        with self.assertRaisesRegex(ValueError, 'Output exists'):self.run_worker(command)
        command.assert_not_called()
        self.assertEqual(self.hists.read_bytes(), b'old-output')

    def test_existing_plot_directory_refuses_execution(self):
        self.plots.mkdir(parents=True)
        from unittest.mock import Mock
        command = Mock()
        with self.assertRaisesRegex(ValueError, 'Output exists'):self.run_worker(command)
        command.assert_not_called()

    def test_missing_export_fails_even_with_successful_command(self):
        def command(argv, **kwargs):self.hists.write_bytes(b'output-without-annotations')
        with self.assertRaisesRegex(ValueError, 'Missing annotation report'):
            self.run_worker(command)

    def test_missing_build_marker_refuses_execution(self):
        (self.dest/'build/ANNOTATIONS_READY').unlink()
        from unittest.mock import Mock
        command = Mock()
        with self.assertRaisesRegex(ValueError, 'prerequisite'):self.run_worker(command)
        command.assert_not_called()

    def test_repeated_success_refuses_overwrite(self):
        self.run_worker(self.write_products)
        with self.assertRaisesRegex(ValueError, 'Output exists'):
            self.run_worker(self.write_products)

if __name__ == '__main__':unittest.main()
