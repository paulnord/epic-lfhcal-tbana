#!/usr/bin/env python3
"""Fetch PS-2026 calibration and SPS parameter-scan raw inputs (Python 3.8+).

One shared file per campaign/run; no fitting or batch submission. The default
operation writes an offline plan. Use --probe to test access, --check for sizes,
or --download to fetch.
"""
import argparse
import concurrent.futures
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
from urllib.parse import urlsplit
import zlib

SOURCE_COMMIT = '5227c3e714e3be16b21a24bb76a99ecb8e85a2a5'
SOURCE_REPO = 'https://github.com/paulnord/epic-lfhcal-tbana'
DATA_DOCUMENTATION = 'https://friederikebock.gitbook.io/epiclfhcaltb-ana/tb-analysis-basics/getting-the-data'
REMOTE_ROOTS = {
    'ps': 'root://dtn-eic.jlab.org:1094//work/eic3/EPIC/TestBeam/LFHCAL/CERN/2026/2026_PST10/raw',
    'sps': 'root://dtn-eic.jlab.org:1094//work/eic3/EPIC/TestBeam/LFHCAL/CERN/2026/2026_SPSH2/raw',
}
LOCAL_DIRS = {'ps': 'ps-2026/raw', 'sps': 'sps-2026/raw'}
STOP = threading.Event()
PRINT_LOCK = threading.Lock()


def say(message):
    with PRINT_LOCK:
        print(message, flush=True)


def catalog():
    # These lists acquire data; inferred pedestal associations are not approvals
    # for using those pedestals in a calibration campaign.
    definitions = [
        ('a1', list(range(86, 93)), 85, 'inferred'),
        ('a2', list(range(121, 127)), 120, 'inferred'),
        ('b1', list(range(189, 194)), 215, 'inferred'),
        ('b2', list(range(217, 221)), 215, 'inferred'),
        ('c1', list(range(131, 137)), 130, 'script-assigned'),
        ('c2', [177, 179, 178, 181, 182, 180, 183, 184], 171, 'script-assigned'),
        ('d1', [242, 241, 240, 244], 238, 'script-assigned; CC mismatch'),
        ('d2', list(range(266, 270)), 265, 'script-assigned'),
        ('e1', list(range(288, 292)), 287, 'script-assigned'),
        ('e2', list(range(316, 321)), 315, 'script-assigned'),
        ('f1', list(range(339, 345)), 338, 'inferred'),
        ('f2', list(range(367, 371)), 366, 'inferred'),
        ('g1', list(range(380, 384)), 379, 'inferred; CC mismatch'),
        ('g2', list(range(405, 409)), 404, 'inferred'),
        ('h1', list(range(427, 431)), 425, 'inferred; merge name needs correction'),
        ('i1', list(range(427, 431)), 425, 'inferred; same muons as H1'),
        ('i2', [464, 463], 462, 'inferred; only listed in recipe comments'),
    ]
    result = {}
    notes = {
        'b1': ['Run 191 is present in the merge list but absent from the active conversion list.',
               'Pedestal dead time is 2000; muons include 1700, 1800 and 2000.'],
        'c1': ['Pedestal dead time is 4000; muons include 4000 and 2000.'],
        'c2': ['Pedestal dead time is 2000; muons use 1500.'],
        'd1': ['Pedestal 238 records CC=3; muons record CC=5. Also fetch 265 (CC=5) for review; no replacement is selected.'],
        'f2': ['Muon runs 367-370 are labelled Muon- beam shutter open.'],
        'g1': ['Pedestal 379 records CC=15; muons record CC=9. Also fetch 404 (CC=9) for review; no replacement is selected.'],
        'h1': ['The FullSetH branch emits a G1 filename. Its board comment says V1 while its conversion uses V2.'],
        'i1': ['The PartSetI branch repeats its first merge twice. Its board comment says V1 while its conversion uses V2.'],
        'i2': ['Runs 463/464 are listed as the second muon set in comments; an active I2 merge is missing.',
               'The board comment says V1 while the conversion uses V2.'],
    }
    for suffix, muons, pedestal, evidence in definitions:
        result['ps-' + suffix] = {
            'campaign': 'ps', 'muon_runs': muons, 'pedestal_runs': [pedestal],
            'pedestal_evidence': evidence,
            'additional_pedestals_for_review': {'d1': [265], 'g1': [404]}.get(suffix, []),
            'notes': notes.get(suffix, []),
        }
    scans = [
        (1, [294, 296, 299, 301, 303, 305], [295, 298, 300, 302, 304, 306], [297]),
        (2, [307, 309], [308, 310], []),
        (3, [328, 330, 332, 334, 336, 338, 340, 342, 344, 346, 348, 350, 352, 354, 356, 358, 360, 362, 364, 367],
            [329, 331, 333, 335, 337, 339, 341, 343, 345, 347, 349, 351, 353, 355, 357, 359, 361, 363, 366, 369], [365, 368]),
    ]
    for number, pedestals, muons, extra in scans:
        result['sps-param' + str(number)] = {
            'campaign': 'sps', 'muon_runs': muons, 'pedestal_runs': pedestals,
            'pedestal_evidence': 'script-assigned per run; never merge different scan settings',
            'pedestal_muon_pairs': [dict(pedestal=p, muon=m) for p, m in zip(pedestals, muons)],
            'extra_raw_runs': extra,
            'notes': ['Group numbers follow calibMuonParScan Set1/Set2/Set3, not the smaller example Yallfile selections.',
                      'Extra raw runs are in the conversion recipe but not its calibration pairs.'] +
                     (['Run 368 records CC=4; pedestal 367 records CC=3. No pair is assigned to extra run 368.'] if number == 3 else []),
        }
    return result


CATALOG = catalog()
GROUPS = {
    'ps': [k for k in CATALOG if k.startswith('ps-')],
    'sps-param': [k for k in CATALOG if k.startswith('sps-')],
    'all': list(CATALOG),
}


def expand_sets(requested):
    names = []
    for token in requested:
        for name in token.lower().split(','):
            if name in GROUPS:
                names.extend(GROUPS[name])
            elif name in CATALOG:
                names.append(name)
            else:
                raise ValueError('Unknown set %r. Use --list.' % name)
    return list(dict.fromkeys(names))


def make_plan(names, out, roots):
    entries = {}
    for name in names:
        item = CATALOG[name]
        for role, field in [('muon', 'muon_runs'), ('pedestal', 'pedestal_runs'),
                            ('pedestal-for-review', 'additional_pedestals_for_review'),
                            ('extra-scan-run', 'extra_raw_runs')]:
            for run in item.get(field, []):
                key = (item['campaign'], run)
                filename = 'Run%03d.h2g' % run
                entry = entries.setdefault(key, {
                    'campaign': key[0], 'run': run, 'filename': filename,
                    'url': roots[key[0]].rstrip('/') + '/' + filename,
                    'local_path': str(out / LOCAL_DIRS[key[0]] / filename), 'used_by': [],
                })
                entry['used_by'].append({'set': name, 'role': role})
    return [entries[k] for k in sorted(entries)]


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp-%d-%d' % (os.getpid(), threading.get_ident()))
    try:
        with temp.open('w') as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write('\n')
        os.replace(str(temp), str(path))
    finally:
        if temp.exists():
            temp.unlink()


def identity(entry):
    return {k: entry[k] for k in ('url', 'size', 'adler32')}


def remote_parts(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('root', 'roots') or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError('Expected a plain root:// or roots:// directory URL: ' + url)
    return parsed.scheme + '://' + parsed.netloc, '/' + parsed.path.lstrip('/')


def command_output(command, timeout):
    if STOP.is_set():
        raise RuntimeError('Interrupted')
    try:
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        details = exc.stderr or exc.stdout or ''
        if isinstance(details, bytes):
            details = details.decode('utf-8', errors='replace')
        raise RuntimeError('%s timed out after %s seconds%s' %
                           (' '.join(command), timeout, ': ' + details.strip()[-2000:] if details.strip() else '')) from exc
    if proc.returncode:
        raise RuntimeError('%s failed: %s' % (' '.join(command), proc.stderr.strip() or proc.stdout.strip()))
    return proc.stdout


def inspect_remote(entry, timeout):
    server, path = remote_parts(entry['url'])
    stat = command_output(['xrdfs', server, 'stat', path], timeout)
    match = re.search(r'^\s*Size:\s*(\d+)\s*$', stat, re.M)
    if not match or int(match.group(1)) <= 0:
        raise RuntimeError('No positive remote file size for ' + entry['url'])
    checksum = command_output(['xrdfs', server, 'query', 'checksum', path], timeout).strip()
    match_sum = re.fullmatch(r'adler32\s+(?:0x)?([0-9a-fA-F]{1,8})', checksum)
    if not match_sum:
        raise RuntimeError('Expected server Adler-32 checksum for %s; got %r' % (entry['url'], checksum))
    return dict(entry, size=int(match.group(1)), adler32=match_sum.group(1).lower().zfill(8))


def preflight(entries, args):
    """Probe one file per campaign first; stop scheduling at the first failure."""
    checked, failures = [], []
    probes, remaining, seen = [], [], set()
    for entry in entries:
        if entry['campaign'] in seen:
            remaining.append(entry)
        else:
            probes.append(entry)
            seen.add(entry['campaign'])

    def record(entry, operation):
        try:
            result = operation()
            checked.append(result)
            say('CHECK %s/%s %d bytes' % (result['campaign'], result['filename'], result['size']))
            return True
        except Exception as exc:
            failures.append({'url': entry['url'], 'error': str(exc)})
            say('ERROR ' + str(exc))
            return False

    for entry in probes:
        say('PROBE ' + entry['url'])
        if not record(entry, lambda: inspect_remote(entry, args.query_timeout)):
            return checked, failures
    if args.probe:
        return checked, failures

    # Bound the number of in-flight operations instead of queuing every file.
    # Running queries may finish, but a failure cannot launch another wave.
    todo = iter(remaining)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        active = {}

        def fill():
            while len(active) < args.jobs:
                entry = next(todo, None)
                if entry is None:
                    break
                active[pool.submit(inspect_remote, entry, args.query_timeout)] = entry

        fill()
        while active:
            done, _ = concurrent.futures.wait(active, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                entry = active.pop(future)
                record(entry, future.result)
            if not failures:
                fill()
    return checked, failures


def adler32(path):
    value = 1
    with Path(path).open('rb') as handle:
        while True:
            if STOP.is_set():
                raise RuntimeError('Interrupted')
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            value = zlib.adler32(chunk, value)
    return '%08x' % (value & 0xffffffff)


def stamp(path):
    st = Path(path).stat()
    return {k: getattr(st, k) for k in ('st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_ino', 'st_dev')}


def read_json(path):
    try:
        with Path(path).open() as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def verify(path, entry):
    before = stamp(path)
    if before['st_size'] != entry['size'] or adler32(path) != entry['adler32']:
        raise RuntimeError('Size/checksum mismatch: %s. File preserved; move it aside before retrying.' % path)
    if stamp(path) != before:
        raise RuntimeError('File changed during verification: ' + str(path))


@contextlib.contextmanager
def file_lock(path):
    # Do not unlink lock files: that would permit two locks on different inodes.
    with Path(path).open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another downloader owns ' + str(path))
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run_copy(command, log=None):
    with (Path(log).open('ab') if log else contextlib.nullcontext(None)) as handle:
        proc = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT if log else None)
        try:
            while proc.poll() is None:
                if STOP.wait(0.5):
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill(); proc.wait()
                    raise RuntimeError('Interrupted; partial file retained')
            return proc.returncode
        finally:
            if proc.poll() is None:
                proc.terminate(); proc.wait()


def download_one(entry, args, request_dir):
    path = Path(entry['local_path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = path.with_name(path.name + '.verified.json')
    partial = path.with_name(path.name + '.part')
    partial_info = path.with_name(path.name + '.part.json')
    log = request_dir / ('%s-%s.log' % (entry['campaign'], path.name))
    with file_lock(path.with_name(path.name + '.lock')):
        expected = identity(entry)
        if path.exists():
            receipt = read_json(receipt_path)
            if not (not args.recheck and isinstance(receipt, dict) and
                    receipt.get('source') == expected and receipt.get('local') == stamp(path)):
                say('VERIFY existing ' + str(path))
                verify(path, entry)
                atomic_json(receipt_path, {'source': expected, 'local': stamp(path)})
            say('OK existing ' + str(path))
            return 'existing'
        if partial.exists():
            if read_json(partial_info) != expected:
                raise RuntimeError('Untracked or changed-source partial file preserved: ' + str(partial))
            if partial.stat().st_size > entry['size']:
                raise RuntimeError('Oversized partial file preserved: ' + str(partial))
        else:
            atomic_json(partial_info, expected)
        for attempt in range(1, args.tries + 1):
            if STOP.is_set():
                raise RuntimeError('Interrupted')
            if partial.exists() and partial.stat().st_size == entry['size']:
                break
            command = ['xrdcp', '--nopbar']
            if partial.exists():
                command.append('--continue')
            command.extend([entry['url'], str(partial)])
            say('COPY %s/%s attempt %d/%d%s' % (entry['campaign'], path.name, attempt, args.tries,
                                              ' (resume)' if '--continue' in command else ''))
            if run_copy(command, log) == 0:
                break
            if attempt == args.tries:
                raise RuntimeError('Transfer failed; partial retained. Log: ' + str(log))
            if STOP.wait(min(2 * attempt, 10)):
                raise RuntimeError('Interrupted')
        say('VERIFY downloaded ' + str(path))
        verify(partial, entry)
        # Atomic publication without overwriting even a file created outside our lock.
        os.link(str(partial), str(path))
        partial.unlink()
        atomic_json(receipt_path, {'source': expected, 'local': stamp(path)})
        partial_info.unlink()
        say('OK downloaded ' + str(path))
        return 'downloaded'


def download_direct(entries, args, request_dir):
    """Match the original tcsh workflow: plain xrdcp, no xrdfs preflight."""
    say('DIRECT: sequential xrdcp, no xrdfs queries or remote checksum comparison.')
    say('Existing nonempty files are skipped. Partial transfers restart from the beginning.')
    completed, failures = [], []
    report = request_dir / 'result.json'
    try:
        for entry in entries:
            if STOP.is_set():
                raise RuntimeError('Interrupted')
            path = Path(entry['local_path'])
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_name(path.name + '.direct.part')
            marker = partial.with_name(partial.name + '.json')
            owner = {'url': entry['url'], 'mode': 'direct'}
            with file_lock(path.with_name(path.name + '.lock')):
                if path.exists():
                    if not path.is_file() or path.stat().st_size == 0:
                        raise RuntimeError('Empty or non-file destination preserved; move aside before retrying: ' + str(path))
                    say('SKIP existing (not checked against source): ' + str(path))
                    completed.append(dict(entry, status='existing-unverified', size=path.stat().st_size))
                    continue
                if partial.is_symlink() or (partial.exists() and read_json(marker) != owner):
                    raise RuntimeError('Untracked direct partial preserved; move aside before retrying: ' + str(partial))
                atomic_json(marker, owner)
                for attempt in range(1, args.tries + 1):
                    if STOP.is_set():
                        raise RuntimeError('Interrupted')
                    if partial.exists():
                        say('RESTART partial: ' + str(partial))
                        partial.unlink()
                    say('COPY %s/%s attempt %d/%d' % (entry['campaign'], path.name, attempt, args.tries))
                    # No flags: use the same xrdcp invocation as download_raw.tcsh.
                    status = run_copy(['xrdcp', entry['url'], str(partial)])
                    if status == 0 and partial.is_file() and partial.stat().st_size > 0:
                        break
                    if attempt == args.tries:
                        raise RuntimeError('Direct copy failed (xrdcp exit=%s); final file not created: %s' % (status, path))
                before = stamp(partial)
                checksum = adler32(partial)
                if stamp(partial) != before:
                    raise RuntimeError('Partial changed while recording local checksum: ' + str(partial))
                os.link(str(partial), str(path))
                partial.unlink()
                marker.unlink()
                completed.append(dict(entry, status='copied', size=before['st_size'],
                                      local_adler32=checksum, remote_checksum_verified=False))
                say('OK copied: ' + str(path))
    except (Exception, KeyboardInterrupt) as exc:
        failures.append({'error': str(exc) or 'Interrupted'})
        say('DIRECT stopped: ' + failures[-1]['error'])
        if isinstance(exc, KeyboardInterrupt):
            raise
    finally:
        atomic_json(report, {'mode': 'direct', 'completed': completed, 'failures': failures,
                            'remote_checksum_verified': False})
    say('Direct result: %d copied/skipped, %d failures. Report: %s' % (len(completed), len(failures), report))
    return 1 if failures else 0


def positive(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError('must be positive')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sets', nargs='+', default=['all'], help='all (default), ps, sps-param, or individual names from --list')
    parser.add_argument('--out', type=Path, help='Shared raw-data directory, preferably on persistent storage')
    parser.add_argument('--list', action='store_true', help='List available sets without writing files')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true', help='Write offline manifests; no network or downloads (default)')
    mode.add_argument('--probe', action='store_true', help='Test metadata access to one raw file per selected campaign; no downloads')
    mode.add_argument('--check', action='store_true', help='Check all remote files/checksums and report bytes; no downloads')
    mode.add_argument('--download', action='store_true', help='Check, download/resume, and verify selected raw files')
    parser.add_argument('--direct', action='store_true', help='With --download: plain sequential xrdcp as in the original tcsh scripts; no xrdfs preflight')
    parser.add_argument('--jobs', type=positive, default=2, help='Concurrent checks/downloads (default 2)')
    parser.add_argument('--tries', type=positive, default=3, help='Transfer attempts per file (default 3)')
    parser.add_argument('--query-timeout', type=positive, default=60, help='Seconds per remote metadata query (default 60)')
    parser.add_argument('--recheck', action='store_true', help='Rehash previously verified local files too')
    parser.add_argument('--ps-source', default=REMOTE_ROOTS['ps'], help='Override PS raw directory URL')
    parser.add_argument('--sps-source', default=REMOTE_ROOTS['sps'], help='Override SPS raw directory URL')
    args = parser.parse_args(argv)
    if args.list:
        print('Aliases: all, ps, sps-param')
        for name, item in CATALOG.items():
            all_runs = set(item['muon_runs'] + item['pedestal_runs'] + item.get('additional_pedestals_for_review', []) + item.get('extra_raw_runs', []))
            print('%-12s %2d files; muons %s; pedestal(s) %s' % (name, len(all_runs), item['muon_runs'], item['pedestal_runs']))
        return 0
    if args.out is None:
        parser.error('--out is required except with --list')
    if args.direct and not args.download:
        parser.error('--direct requires --download')
    if args.direct and args.recheck:
        parser.error('--recheck requires the normal checksum-verified mode, without --direct')
    names = expand_sets(args.sets)
    roots = {'ps': args.ps_source, 'sps': args.sps_source}
    for root in roots.values(): remote_parts(root)
    out = args.out.expanduser().absolute()
    entries = make_plan(names, out, roots)
    token = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-%d' % os.getpid()
    request_dir = out / 'manifests' / token
    request_dir.mkdir(parents=True)
    provenance = {
        'source_repo': SOURCE_REPO, 'source_commit': SOURCE_COMMIT, 'data_documentation': DATA_DOCUMENTATION,
        'recipe_files': ['NewStructure/convertDataHGCROC_TBPST10_2026.sh', 'NewStructure/runHGCROCCalibration_TBPST10_2026.sh',
                         'NewStructure/convertDataHGCROC_TBSPSH2_2026.sh', 'NewStructure/runHGCROCCalibration_TBSPSH2_2026.sh'],
        'selected_sets': names, 'files': entries, 'direct_copy': args.direct,
        'scope': 'Named PS muon sets A1-I2 and all SPS ParameterScan raw inputs. No pion/hadron samples or separate PS voltage/position scans.',
    }
    atomic_json(request_dir / 'plan.json', provenance)
    for name in names:
        atomic_json(request_dir / (name + '.json'), dict(CATALOG[name], set=name, source_commit=SOURCE_COMMIT,
                    files=[e for e in entries if any(u['set'] == name for u in e['used_by'])]))
    say('Selected: ' + ', '.join(names))
    for campaign in ('ps', 'sps'):
        selected = [e for e in entries if e['campaign'] == campaign]
        say('%s: %d unique raw files -> %s' % (campaign.upper(), len(selected), out / LOCAL_DIRS[campaign]))
    say('Manifests: ' + str(request_dir))
    for name in names:
        for note in CATALOG[name]['notes']: say('NOTE %s: %s' % (name, note))
    if not (args.probe or args.check or args.download):
        for e in entries: say('%s -> %s' % (e['url'], e['local_path']))
        say('Offline plan only. Use --probe to test access, --check for sizes, or --download to transfer.')
        return 0
    required = ['xrdcp'] if args.direct else (['xrdfs', 'xrdcp'] if args.download else ['xrdfs'])
    for command in required:
        if shutil.which(command) is None:
            raise RuntimeError('%s is unavailable. Run this inside eic-shell (or an XRootD client environment).' % command)
    if args.direct:
        say('XRootD copy client: ' + shutil.which('xrdcp'))
        return download_direct(entries, args, request_dir)
    say('XRootD client: ' + shutil.which('xrdfs'))
    checked, failures = preflight(entries, args)
    checked.sort(key=lambda e: (e['campaign'], e['run']))
    accounted = {e['url'] for e in checked + failures}
    atomic_json(request_dir / 'remote-manifest.json', {
        'files': checked, 'failures': failures, 'probe_only': args.probe,
        'unchecked': [e['url'] for e in entries if e['url'] not in accounted],
    })
    if failures:
        say('Preflight stopped after a failed query. No raw transfers started.')
        say('A timeout does not establish that a file is missing. Retry --probe inside your EIC shell to compare clients/access.')
        return 1
    if args.probe:
        say('Probe complete: %d file(s) checked. Remaining files have not been checked; use --check for the full list.' % len(checked))
        return 0
    if len(checked) != len(entries):
        say('Incomplete preflight. No raw transfers started.')
        return 1
    needed = 0
    for e in checked:
        path = Path(e['local_path']); partial = path.with_name(path.name + '.part')
        if not path.exists():
            reusable = partial.stat().st_size if partial.exists() and read_json(path.with_name(path.name + '.part.json')) == identity(e) else 0
            needed += max(0, e['size'] - reusable)
    total = sum(e['size'] for e in checked)
    free = shutil.disk_usage(str(out)).free
    say('Remote total: %.2f GiB; additional file bytes: %.2f GiB; filesystem free: %.2f GiB (quota not checked).' %
        (total / 2**30, needed / 2**30, free / 2**30))
    if args.check:
        say('Remote preflight complete. Existing local contents have not been verified; --download verifies or reuses receipts.')
        return 0
    if needed > free:
        raise RuntimeError('Insufficient filesystem free space; no raw transfers started.')
    completed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        tasks = {pool.submit(download_one, e, args, request_dir): e for e in checked}
        for future in concurrent.futures.as_completed(tasks):
            entry = tasks[future]
            try:
                completed.append({'local_path': entry['local_path'], 'status': future.result()})
            except Exception as exc:
                failures.append({'local_path': entry['local_path'], 'error': str(exc)})
                say('ERROR ' + str(exc))
    atomic_json(request_dir / 'result.json', {'completed': completed, 'failures': failures})
    say('Finished: %d verified files, %d failures. Report: %s' % (len(completed), len(failures), request_dir / 'result.json'))
    return 1 if failures else 0


def interrupted(signum, frame):
    STOP.set()
    raise KeyboardInterrupt


if __name__ == '__main__':
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say('Interrupted. Completed files and any partial files are retained.')
        sys.exit(130)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        say('ERROR: ' + str(exc))
        sys.exit(1)
