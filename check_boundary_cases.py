#!/usr/bin/env python3
"""Read-only review safeguards; no rendering or physical fit validation."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import plot_boundary_cases as review


class Histogram:
    def GetNbinsX(self): return 2
    def GetBinContent(self, i): return [0., 10., 20., 0.][i]
    def GetXaxis(self): return self
    def GetXmin(self): return 0.
    def GetXmax(self): return 2.
    def GetBinCenter(self, i): return i-.5
    def GetBinError(self, i): return [float('nan'), 3.][i-1]


class Graph:
    def __init__(self, *args): self.args = args
    def SetMarkerStyle(self, x): pass
    def SetMarkerSize(self, x): pass
    def SetLineColor(self, x): pass


class Checks(unittest.TestCase):
    def test_histogram_parameters_range_and_nonfinite_errors(self):
        h = Histogram()
        digest = hashlib.sha256(json.dumps(dict(counts=[0.,10.,20.,0.], nbins=2,
                                 xmin=0., xmax=2.), sort_keys=True).encode()).hexdigest()
        row = dict(fit_saved='True', histogram_present='True', histogram_sha256=digest,
                   landau_width='2', mpv='40', area='500', gaussian_sigma='8',
                   fit_xmin='10', fit_xmax='100', range_new='10')
        data = dict(hist=h, fit=True, parameters=[2.,40.,500.,8.], xmin=10., xmax=100.)
        review.verify_channel(data, row)
        for change in ({'fit_saved':'False'}, {'landau_width':'3'}, {'fit_xmin':'12'},
                       {'range_new':'15'}, {'histogram_sha256':'wrong'}):
            with self.assertRaises(ValueError): review.verify_channel(data, dict(row, **change))
        root = type('Root', (), dict(TGraphErrors=Graph, kBlack=1))
        review.histogram_graph(root, data)
        self.assertEqual(data['bad_error_bins'], 1)
        self.assertEqual(list(data['point_y']), [10., 20.])
        self.assertEqual(list(data['point_error']), [0., 3.])
        self.assertNotEqual(h.GetBinError(1), h.GetBinError(1))  # Original remains NaN.

    def test_original_resolution_frozen_hash_and_history_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); references = []; old = root/'old-extension'
            for model in review.MODELS:
                for stage in ['mip']+[f'refine{n}' for n in range(1,9)]:
                    row = dict(dataset='b2', model=model, stage=stage, cell_id=704,
                               fit_saved=stage!='refine7', scale_h='40' if stage=='mip' else '44',
                               mpv=42, landau_width=3, gaussian_sigma=8, fit_xmin=10)
                    for prefix in ('references', ''):
                        relative = Path(prefix)/model/'b2'/stage/'cells.csv'
                        path = root/relative; path.parent.mkdir(parents=True, exist_ok=True)
                        with path.open('w', newline='') as f:
                            w=csv.DictWriter(f, fieldnames=list(row)); w.writeheader(); w.writerow(row)
                        if prefix:
                            references.append(dict(copy=str(relative), original=str(old/model/'b2'/stage/'cells.csv'),
                                                   sha256=review.spectra.sha(path)))
            (root/'manifest.json').write_text(json.dumps(dict(reference_files=references)))
            with patch.object(review, 'CASES', {'b2':{704:'test'}}):
                _, records, _ = review.collect(root, ['b2'])
                self.assertEqual(records['b2','original','legacy','refine8',704]['folder'], old/'legacy/b2/refine8')
                path = root/'history.csv'; review.write_history(path, records)
                with path.open() as f: rows = list(csv.DictReader(f))
                self.assertEqual(len(rows), 36)
                self.assertTrue(all(r['step_fraction_scale_h']=='' for r in rows if r['stage'] in ('refine7','refine8')))
                self.assertTrue(all(float(r['step_fraction_scale_h'])==.1 for r in rows if r['stage']=='refine1'))
                bad = root/references[0]['copy']; bad.write_text(bad.read_text()+'\n')
                with self.assertRaisesRegex(ValueError, 'Frozen reference changed'):
                    review.collect(root, ['b2'])


if __name__ == '__main__':
    unittest.main()
