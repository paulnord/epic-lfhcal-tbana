#!/usr/bin/env python3
"""Apply a small HGCROC-only patch to the original 100-step fitter.

Default is a dry run (unified diff). --apply checks the exact original blob,
then writes only NewStructure/TileSpectra.cc. It never switches branches,
commits, pushes, changes calibration data, or patches a different source version.
"""
import argparse
import difflib
import hashlib
from pathlib import Path

BASE_COMMIT = '924ad82de6d150534b4d7684b5638df92c0a2016'
BASE_BLOB = '80fdbaca75d727e9d7451c3d5e3d0626d1d13808'
RELATIVE_SOURCE = Path('NewStructure/TileSpectra.cc')


def git_blob_sha(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected one source anchor: '+repr(old))
    return text.replace(old, new, 1)


def transform(source):
    source = once(source, '#include "TileSpectra.h"\n',
                  '#include "TileSpectra.h"\n#include "AdaptiveLangau.h"\n')
    begin = source.index('bool TileSpectra::FitMipHG(')
    end = source.index('//***********************************************************************************\n'
                       '// fitting for minimum ionizing peak for LG CAEN readout', begin)
    before, body, after = source[:begin], source[begin:end], source[end:]
    body = once(body, 'double avmip = -1000){', 'double avmip = -1000) try {')
    body = once(body, 'double* fitrange    = new double[2];', 'double fitrange[2];')
    body = once(body, 'double* startvalues    = new double[4];', 'double startvalues[4];')
    body = once(body, 'double* parlimitslo    = new double[4];', 'double parlimitslo[4];')
    body = once(body, 'double* parlimitshi    = new double[4];', 'double parlimitshi[4];')
    body = once(body,
        '  SignalHG = TF1(funcName.Data(),langaufun,fitrange[0],fitrange[1],4);',
        '''  // Only HGCROC switches evaluator; the existing fitter is retained.
  auto model = langaufun;
  if (ROType == ReadOut::Type::Hgcroc)
    model = +[](double* x, double* p) {
      return lfhcal::adaptive_langau::Convolution(
          {p[0],p[1],p[2],p[3]},
          [](double u) { return TMath::Landau(u,0.,1.); })(x[0]);
    };
  SignalHG = TF1(funcName.Data(),model,fitrange[0],fitrange[1],4);
  if (ROType == ReadOut::Type::Hgcroc)
    SignalHG.SetTitle("Landau-Gaussian (adaptive, +/-5 sigma)");''')
    body = once(body, '    SignalHG.GetParameters(out);    // obtain fit parameters',
        '''    // Compute the calibration from the SAME continuous model as the fit.
    // Do this before updating caller outputs or the preceding calibration.
    double fitted[4], SNRPeak, SNRFWHM;
    SignalHG.GetParameters(fitted);
    if (ROType == ReadOut::Type::Hgcroc) {
      const auto width = lfhcal::adaptive_langau::peakWidth(
          [&](double x) { return SignalHG.Eval(x); },
          fitted[1], std::max(fitted[0],fitted[3]));
      SNRPeak = width.peak;
      SNRFWHM = width.fwhm;
    } else {
      langaupro(fitted,SNRPeak,SNRFWHM);
    }
    SignalHG.GetParameters(out);    // obtain fit parameters''')
    body = once(body, '    double SNRPeak, SNRFWHM;\n    langaupro(out,SNRPeak,SNRFWHM);\n', '')
    for name in ('fitrange','startvalues','parlimitslo','parlimitshi'):
        body = once(body, '  delete '+name+';\n', '')
    body = once(body, '  return bmipHG;\n}', '''  return bmipHG;
} catch (const std::exception& error) {
  bmipHG = false;
  std::cerr << "Skipped HG cell " << cellID << " numerical failure: "
            << error.what() << std::endl;
  return false;
}''')
    return before+body+after


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    path = args.repo/RELATIVE_SOURCE
    helper = args.repo/'NewStructure/AdaptiveLangau.h'
    data = path.read_bytes()
    actual = git_blob_sha(data)
    if actual != BASE_BLOB:
        ap.error(f'Refusing to change {path}: blob {actual} differs from '
                 f'{BASE_BLOB} at {BASE_COMMIT}. Use a clean worktree of that base.')
    if not helper.is_file():
        ap.error('AdaptiveLangau.h must be present before applying the core patch')
    source = data.decode('utf-8')
    changed = transform(source)
    print(''.join(difflib.unified_diff(source.splitlines(True), changed.splitlines(True),
        fromfile='a/'+str(RELATIVE_SOURCE), tofile='b/'+str(RELATIVE_SOURCE))), end='')
    if args.apply:
        temp = path.with_name(path.name+'.adaptive-tmp')
        if temp.exists():
            ap.error(f'Refusing to overwrite temporary file {temp}')
        temp.write_text(changed, encoding='utf-8')
        temp.chmod(path.stat().st_mode)
        temp.replace(path)
        print('\nApplied to TileSpectra.cc only; inspect git diff before committing.')
    else:
        print('\nDry run only. Add --apply to write this exact core patch.')


if __name__ == '__main__':
    main()
