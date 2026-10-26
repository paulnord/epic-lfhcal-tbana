"""Exact raw Git-byte regression. Set LFHCAL_TEST_NETWORK=1 to test live transport."""
import ast
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import urllib.request

SOURCE=Path(__file__).resolve().parents[1]/'run.py'
REVISION='51a43cb548edeb6a418be037a402ae1e21387c23'
# Blob IDs independently read from GitHub's base64 file endpoint at REVISION.
PINS={
    'PlotHelper.h':(92874,'a80231a7c58736689fc0d91cd32e27d56d9c2dbdf5273c81263371e3c18a0ab6','c3d519b8d6d407f715ac532135eef2029a4480b6'),
    'FitCurveDrawing.h':(3035,'173e7dbdab857d0eae448caee32ef9cb585c04457546ba38803091adced54fbc','51803f967146f8abcaaa80fef386737adccec987'),
}

class SourcePins(unittest.TestCase):
    def test_exact_raw_pins_in_launcher(self):
        tree=ast.parse(SOURCE.read_text())
        loop=next(n for n in tree.body if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple)
                  and [x.id for x in n.target.elts]==['name','digest'])
        self.assertEqual(dict(ast.literal_eval(loop.iter)),{k:v[1] for k,v in PINS.items()})
        revision=next(n for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id=='revision')
        self.assertEqual(ast.literal_eval(revision.value),REVISION)

    def test_added_newline_is_rejected_with_hash_diagnostics(self):
        tree=ast.parse(SOURCE.read_text())
        definitions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('need','sha','pin')]
        scope={'hashlib':hashlib}
        exec(compile(ast.Module(body=definitions,type_ignores=[]),str(SOURCE),'exec'),scope)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'header.h'; raw=b'#endif\n'; path.write_bytes(raw)
            digest=hashlib.sha256(raw).hexdigest(); scope['pin'](path,digest)
            path.write_bytes(raw+b'\n')
            with self.assertRaisesRegex(RuntimeError,'expected SHA256 '+digest+', got '): scope['pin'](path,digest)

    @unittest.skipUnless(os.environ.get('LFHCAL_TEST_NETWORK')=='1','opt-in live GitHub transport')
    def test_live_raw_transport_matches_git_blobs(self):
        for name,(size,sha256,blob) in PINS.items():
            with self.subTest(name=name):
                url='https://raw.githubusercontent.com/eic/epic-lfhcal-tbana/'+REVISION+'/NewStructure/'+name
                with urllib.request.urlopen(url,timeout=90) as response: raw=response.read()
                self.assertEqual(len(raw),size)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),sha256)
                self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),blob)

if __name__=='__main__': unittest.main()
