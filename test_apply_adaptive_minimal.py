"""Source-patch tests. Numerical tests exercise the actual C++ helper separately."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from apply_adaptive_minimal import SUPPORTED_BASE_BLOBS, git_blob_sha, once, transform


# Only patch anchors are modeled here. These tests do not compile TileSpectra.
FIXTURE = '''#include "TileSpectra.h"
// unrelated code before
bool TileSpectra::FitMipHG(double* out, double* outErr, double avmip = -1000){
  double* fitrange    = new double[2];
  double* startvalues    = new double[4];
  double* parlimitslo    = new double[4];
  double* parlimitshi    = new double[4];
  SignalHG = TF1(funcName.Data(),langaufun,fitrange[0],fitrange[1],4);
  // original fit options, status and bounds remain here
  if (bmipHG){
    SignalHG.GetParameters(out);    // obtain fit parameters
    double SNRPeak, SNRFWHM;
    langaupro(out,SNRPeak,SNRFWHM);
    calib->ScaleH = SNRPeak;
    calib->ScaleWidthH = SNRFWHM;
  }
  delete fitrange;
  delete startvalues;
  delete parlimitslo;
  delete parlimitshi;
  return bmipHG;
}
//***********************************************************************************
// fitting for minimum ionizing peak for LG CAEN readout
bool TileSpectra::FitMipLG() {return true;}
// untouched historical langaufun, calibration and selection code
'''


class PatchTests(unittest.TestCase):
    def test_exact_blob_hash_format(self):
        self.assertEqual(git_blob_sha(b''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')

    def test_lg_and_remaining_source_untouched(self):
        result=transform(FIXTURE)
        start=FIXTURE.index('//***********************************************************************************')
        self.assertTrue(result.endswith(FIXTURE[start:]))
        self.assertIn('// unrelated code before',result)

    def test_one_fitter_no_retry(self):
        result=transform(FIXTURE)
        self.assertEqual(result.count('bool TileSpectra::FitMipHG('),1)
        self.assertIn('auto model = langaufun;',result)
        self.assertIn('ROType == ReadOut::Type::Hgcroc',result)
        self.assertIn('original fit options, status and bounds remain here',result)
        self.assertNotIn('new double[',result)
        self.assertNotIn('delete fitrange',result)

    def test_peak_before_publication(self):
        result=transform(FIXTURE)
        self.assertLess(result.index('peakWidth('),result.index('SignalHG.GetParameters(out)'))
        self.assertLess(result.index('peakWidth('),result.index('calib->ScaleH ='))
        self.assertIn('catch (const std::exception& error)',result)
        self.assertIn('bmipHG = false;',result)

    def test_reapply_refused(self):
        with self.assertRaises(ValueError): transform(transform(FIXTURE))

    def test_stack_array_base_produces_same_adaptive_fitter(self):
        source = FIXTURE
        for name, size in (('fitrange', 2), ('startvalues', 4),
                           ('parlimitslo', 4), ('parlimitshi', 4)):
            source = source.replace(f'double* {name}    = new double[{size}];',
                                    f'double {name}[{size}];')
            source = source.replace('  delete '+name+';\n', '')
        self.assertEqual(transform(source), transform(FIXTURE))

    def test_current_source_is_supported_and_lg_is_preserved(self):
        source = Path(__file__).with_name('NewStructure').joinpath('TileSpectra.cc').read_bytes()
        self.assertIn(git_blob_sha(source), SUPPORTED_BASE_BLOBS)
        text = source.decode('utf-8')
        start = text.index('bool TileSpectra::FitMipLG(')
        self.assertTrue(transform(text).endswith(text[start:]))

    def test_cli_rejects_unrecognized_source_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo/'NewStructure').mkdir()
            source = repo/'NewStructure/TileSpectra.cc'
            source.write_text(FIXTURE)
            (repo/'NewStructure/AdaptiveLangau.h').write_text('// test helper\n')
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('apply_adaptive_minimal.py')),
                                     '--repo', str(repo), '--apply'],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Refusing to change', result.stderr)
            self.assertEqual(source.read_text(), FIXTURE)

    def test_missing_and_duplicate_anchor_refused(self):
        for text in ('no anchor','xx xx'):
            with self.assertRaises(ValueError): once(text,'xx','yy')


if __name__ == '__main__': unittest.main()
