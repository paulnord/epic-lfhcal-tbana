"""Regression for the production float-subtraction metadata, not rounded text."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'replay.cc'

class CalibrationMetadata(unittest.TestCase):
    @unittest.skipUnless(shutil.which('c++'),'requires a C++ compiler')
    def test_original_float_metadata_and_wrong_values(self):
        source=SOURCE.read_text()
        declaration=re.search(r'const double expectedVov=[^;]+;',source).group()
        self.assertIn('demand(final->GetVov()==expectedVov,',source)
        program='''
#include <map>
#include <cassert>
struct RunInfo { float vop; float vbr; };
int main() {
  std::map<int,RunInfo> runs{{421,{44.f,38.3f}}};
  DECLARATION
  // Value printed from the genuine archived Calib by ROOT Scan, precision17.
  assert(expectedVov==5.7000007629394531);
  assert(expectedVov!=5.7); // The old synthetic fixture hid this precision defect.
  assert(expectedVov!=4.7000007629394531);
}
'''.replace('DECLARATION',declaration)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); (path/'test.cc').write_text(program)
            subprocess.run(['c++','-std=c++17',str(path/'test.cc'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)

if __name__=='__main__': unittest.main()
