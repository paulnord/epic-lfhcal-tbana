#!/usr/bin/env python3
"""Inspect HGCROC conversion counters and merged entry counts without reading events."""
import argparse
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--converted', type=Path, required=True)
    p.add_argument('--runs', type=int, nargs='+', required=True, help='Muon runs included in the merge')
    p.add_argument('--pedestal', type=int, nargs='*', default=[])
    p.add_argument('--merged', help='Merged ROOT filename, relative to --converted, or an absolute path')
    p.add_argument('--raw-dir', type=Path, help='Optional directory containing RunNNN.h2g')
    args = p.parse_args()
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.gErrorIgnoreLevel = ROOT.kError  # Dictionaries are unnecessary for these metadata reads.
    failures = []
    entries = {}

    def open_data(path):
        if not path.is_file():
            raise ValueError('file missing')
        f = ROOT.TFile.Open(str(path), 'READ')
        if not f or f.IsZombie():
            if f:
                f.Close()
            raise ValueError('cannot open ROOT file')
        if f.TestBit(ROOT.TFile.kRecovered):
            f.Close()
            raise ValueError('ROOT recovered an uncleanly closed file')
        t = f.Get('Data')
        if not t or not t.InheritsFrom('TTree'):
            f.Close()
            raise ValueError('Data tree missing')
        return f, int(t.GetEntries())

    print('Run  Type       Raw-GiB ROOT-GiB Data-entries Decoded-events Read-packets Corrupt-packets Tree-minus-decoded')
    for run in sorted(set(args.runs + args.pedestal)):
        path = args.converted / ('rawHGCROC_%d.root' % run)
        f = None
        try:
            f, n = open_data(path)
            h = f.Get('hNEvents')
            if not h or not h.InheritsFrom('TH1') or h.GetNbinsX() < 5:
                raise ValueError('hNEvents conversion counters missing')
            decoded, packets, corrupt = (int(h.GetBinContent(i)) for i in (2, 3, 4))
            raw = args.raw_dir / ('Run%03d.h2g' % run) if args.raw_dir else None
            raw_size = '%.3f' % (raw.stat().st_size / 2**30) if raw and raw.is_file() else '-'
            kind = 'pedestal' if run in args.pedestal else 'muon'
            print('%3d  %-9s %7s %8.3f %12d %14d %12d %15d %+d' %
                  (run, kind, raw_size, path.stat().st_size / 2**30, n, decoded, packets, corrupt, n-decoded))
            entries[run] = n
            if decoded <= 0 or packets <= 0 or n-decoded not in (0, 1):
                failures.append('Run%d: inconsistent or empty conversion counters' % run)
            if corrupt:
                print('NOTE Run%d: inspect conversion log for %d corrupted packets.' % (run, corrupt))
        except (OSError, ValueError) as e:
            failures.append('Run%d: %s' % (run, e))
        finally:
            if f:
                f.Close()

    if args.merged:
        path = args.converted / args.merged
        f = None
        try:
            f, actual = open_data(path)
            if not all(run in entries for run in set(args.runs)):
                raise ValueError('cannot compare merge: an input could not be checked')
            expected = sum(entries[run] for run in set(args.runs))
            print('MERGE %s: %d entries; sum of muon inputs = %d; %s' %
                  (path.name, actual, expected, 'MATCH' if actual == expected else 'MISMATCH'))
            if actual != expected:
                failures.append('merged entry count differs from sum of muon inputs')
        except (OSError, ValueError) as e:
            failures.append('Merged file: %s' % e)
        finally:
            if f:
                f.Close()

    print('A +1 tree/decoder difference is consistent with the existing final extra Fill() in the converter.')
    print('These are recorded conversion counters; they do not independently prove that every raw packet was read.')
    for failure in failures:
        print('CHECK:', failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
