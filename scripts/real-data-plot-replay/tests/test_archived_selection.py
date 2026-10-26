"""Small synthetic checksum fixtures; never read or manufacture the 5.62 GB input."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('archived_selection',Path(__file__).resolve().parents[1]/'archived_selection.py')
MODULE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)

class ArchiveSelection(unittest.TestCase):
    def test_independently_recorded_constants(self):
        self.assertEqual(MODULE.SIZE,5622928634)
        self.assertEqual(MODULE.SHA256,'aaf20ad783d42c86f6a706d9423fb5e19a0125f066ffc0ff2e9eb409d592bc41')
        self.assertEqual(MODULE.TREES,{'Data':681628,'Setup':5,'Calib':1})
        self.assertEqual(MODULE.STAGE_SHA256,'60c1ca8cacd8fb92136c1ddbb215c35f4e49e737656c9e2c998b3ac5b2dd82a8')

    def fixture(self,change=None,damage=None):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); campaign=root/MODULE.CAMPAIGN; boundary=root/MODULE.BOUNDARY
            events=boundary/MODULE.RELATIVE;events.parent.mkdir(parents=True)
            content=b'synthetic selected events';events.write_bytes(content)
            stage=campaign/'legacy/e2/select/stage.json';stage.parent.mkdir(parents=True)
            stage.write_text(json.dumps(dict(model='legacy',dataset='e2',stage='select',event_trees=MODULE.TREES)))
            event_hash=MODULE.digest(events);stage_hash=MODULE.digest(stage)
            entry=lambda name:dict(path='/gpfs/mnt/gpfs01/star/scratch/pnord/lfhcal/'+name+'/'+str(MODULE.RELATIVE),size=len(content),sha256=event_hash)
            record=dict(model='legacy',dataset='e2',boundary='after original event selection; before refine1',
                        event_trees=MODULE.TREES,selected=entry(MODULE.BOUNDARY),original_selected=entry(MODULE.CAMPAIGN),reference_sha256=stage_hash)
            if change: change(record)
            ready=boundary/'inputs/legacy/e2/ready.json';ready.parent.mkdir(parents=True);ready.write_text(json.dumps(record))
            if damage: damage(events,stage,ready)
            before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(MODULE,'SIZE',len(content)),patch.object(MODULE,'SHA256',event_hash),patch.object(MODULE,'STAGE_SHA256',stage_hash):
                result=MODULE.verify(campaign,events)
            self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertEqual(result['sha256'],event_hash)

    def test_valid_read_only_override(self): self.fixture()
    def test_wrong_dataset(self):
        with self.assertRaisesRegex(RuntimeError,'wrong method/dataset'): self.fixture(lambda r:r.update(dataset='b2'))
    def test_wrong_original_path(self):
        with self.assertRaisesRegex(RuntimeError,'wrong original identity'):
            self.fixture(lambda r:r['original_selected'].update(path='/wrong/campaign.root'))
    def test_wrong_recorded_hash(self):
        with self.assertRaisesRegex(RuntimeError,'wrong size/hash'):
            self.fixture(lambda r:r['selected'].update(sha256='0'*64))
    def test_wrong_candidate_hash(self):
        with self.assertRaisesRegex(RuntimeError,'file SHA256 differs'):
            self.fixture(damage=lambda e,s,r:e.write_bytes(b'X'+e.read_bytes()[1:]))
    def test_wrong_candidate_size(self):
        with self.assertRaisesRegex(RuntimeError,'file size differs'):
            self.fixture(damage=lambda e,s,r:e.write_bytes(e.read_bytes()+b'X'))
    def test_wrong_original_stage_bytes(self):
        with self.assertRaisesRegex(RuntimeError,'select/stage.json differs'):
            self.fixture(damage=lambda e,s,r:s.write_text(s.read_text()+' '))
    def test_missing_ready(self):
        with self.assertRaisesRegex(RuntimeError,'missing copy-provenance record'):
            self.fixture(damage=lambda e,s,r:r.unlink())

if __name__=='__main__': unittest.main()
