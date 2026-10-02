#!/usr/bin/env python3
"""Synthetic ROOT/PDF integration check. Requires PyROOT, pypdf, Matplotlib.

Writes test artifacts only, never real calibration plots. Reproduces the old
tiny-canvas failure, validates all repaired ROOT pages, and tests PNG rebuilding.
"""
from array import array
import argparse
import json
import math
from pathlib import Path
import ROOT
from pypdf import PdfReader
import plot_boundary_cases as review
from rebuild_case_pdfs import rebuild


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=False)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0); ROOT.gStyle.SetOptTitle(1)
    stages = ['refine6', 'refine7', 'refine8']
    data = {}
    for boundary in review.BOUNDARIES:
        for model in review.MODELS:
            for stage in stages:
                xs = array('d', range(101))
                ys = array('d', [60*math.exp(-.5*((x-40)/9)**2) for x in xs])
                points = ROOT.TGraph(len(xs), xs, ys)
                points.SetMarkerStyle(20); points.SetMarkerSize(.4)
                curve = ROOT.TGraph(len(xs), xs, ys)
                curve.SetLineColor(ROOT.kOrange+7 if model=='legacy' else ROOT.kAzure+2)
                curve.SetLineWidth(2)
                row = dict(scale_h=40, mpv=38, landau_width=3, gaussian_sigma=8,
                           fit_xmin=15, fit_xmax=90, entries=2000, chi2_ndf=1.2,
                           range_status='raised')
                data[boundary, model, stage] = dict(row=row, points=points, graph=curve,
                    fit=True, hist=True, xmin=15, xmax=90, bad_error_bins=0)
    for broken in (True, False):
        pdf = a.out/('broken.pdf' if broken else 'fixed-root.pdf')
        book = ROOT.TCanvas('book', 'book', 10 if broken else 1800, 10 if broken else 700)
        if not broken: book.SetCanvasSize(1800, 700)
        book.Print(str(pdf)+'[')
        for boundary in review.BOUNDARIES:
            for model in review.MODELS:
                png = a.out/f'b2-cell704-{boundary}-{model}.png'
                review.draw(ROOT, 'b2', 704, boundary, model, stages, data, (0,100,70), png, pdf)
        book.Print(str(pdf)+']'); book.Close()
        pages = PdfReader(pdf).pages
        assert len(pages)==4
        boxes = [(float(x.cropbox.height),float(x.cropbox.width)) if x.rotation%180 else
                 (float(x.cropbox.width),float(x.cropbox.height)) for x in pages]
        print('ROOT', ROOT.gROOT.GetVersion(), pdf.name, boxes)
        if broken:
            assert any(w<1 or h<1 for w,h in boxes), 'Could not reproduce old failure'
        else:
            assert all(w>100 and h>100 for w,h in boxes), 'Degenerate fixed page'
            assert all(abs(w/h-1800/700)<.03 for w,h in boxes), 'Wrong page aspect ratio'
            assert all('refine8' in x.extract_text() for x in pages), 'Missing panel text'
    (a.out/'manifest.json').write_text(json.dumps(dict(cases={'b2':{'704':'synthetic render test'}})))
    rebuilt = rebuild(a.out, a.out/'rebuilt')/'b2-cases.pdf'
    pages = PdfReader(rebuilt).pages
    assert len(pages)==4
    for page in pages:
        assert page.cropbox.width > 100 and page.cropbox.height > 100
        assert abs(float(page.cropbox.width/page.cropbox.height)-1800/700)<.03
        assert len(page.images)>0, 'No embedded PNG page'
    print('PASS: old failure reproduced; fixed ROOT export and PNG rebuild have four nondegenerate pages.')


if __name__ == '__main__':
    main()
