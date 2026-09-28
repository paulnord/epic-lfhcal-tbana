"""Source-patch tests. Numerical tests exercise the actual C++ helper separately."""
import hashlib
import unittest
from apply_adaptive_minimal import git_blob_sha, once, transform


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

    def test_missing_and_duplicate_anchor_refused(self):
        for text in ('no anchor','xx xx'):
            with self.assertRaises(ValueError): once(text,'xx','yy')


if __name__ == '__main__': unittest.main()
