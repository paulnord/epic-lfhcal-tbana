"""Read-only recovery of the independently recorded original E2 selection copy."""
import hashlib
import json
from pathlib import Path

CAMPAIGN='adaptive-fullchains-remaining-20260929T014858Z'
BOUNDARY='boundary-fullchains-20261002'
RELATIVE=Path('legacy/e2/select/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_FullSetE_2.root')
SHA256='aaf20ad783d42c86f6a706d9423fb5e19a0125f066ffc0ff2e9eb409d592bc41'
SIZE=5622928634
TREES={'Data':681628,'Setup':5,'Calib':1}
STAGE_SHA256='60c1ca8cacd8fb92136c1ddbb215c35f4e49e737656c9e2c998b3ac5b2dd82a8'

def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''): value.update(block)
    return value.hexdigest()

def require(condition,why):
    if not condition: raise RuntimeError('Archived selection: '+why)

def normalized(path):
    return str(path).replace('/gpfs/mnt/gpfs01/','/gpfs01/',1)

def verify(campaign,events):
    campaign=Path(campaign).resolve(); events=Path(events).resolve()
    require(campaign.name==CAMPAIGN,'wrong original campaign')
    require(events.is_file(),'missing explicit event file: '+str(events))
    require(tuple(events.parts[-4:])==RELATIVE.parts,'not the legacy E2 selected-event path')
    boundary=events.parents[3]
    require(boundary.name==BOUNDARY,'not the recorded boundary-copy campaign')
    ready=boundary/'inputs/legacy/e2/ready.json'
    require(ready.is_file(),'missing copy-provenance record: '+str(ready))
    record=json.loads(ready.read_text())
    require((record.get('model'),record.get('dataset'))==('legacy','e2'),'wrong method/dataset')
    require(record.get('boundary')=='after original event selection; before refine1','wrong processing boundary')
    require(record.get('event_trees')==TREES,'wrong original tree counts')
    require(record.get('reference_sha256')==STAGE_SHA256,'wrong original selection-report hash')
    for field,root in [('selected',BOUNDARY),('original_selected',CAMPAIGN)]:
        entry=record.get(field,{})
        expected='/gpfs01/star/scratch/pnord/lfhcal/'+root+'/'+str(RELATIVE)
        require(normalized(entry.get('path',''))==expected,field+' has wrong original identity')
        require(entry.get('size')==SIZE and entry.get('sha256')==SHA256,field+' has wrong size/hash')
    stage=campaign/'legacy/e2/select/stage.json'
    require(stage.is_file() and digest(stage)==STAGE_SHA256,'original select/stage.json differs')
    original=json.loads(stage.read_text())
    require((original.get('model'),original.get('dataset'),original.get('stage'))==('legacy','e2','select'),
            'wrong original selection report identity')
    require(original.get('event_trees')==TREES,'original report tree counts differ')
    before=events.stat()
    require(before.st_size==SIZE,'candidate file size differs')
    print('Verifying archived original E2 selection: 5.62 GB SHA256 read (no copy).',flush=True)
    require(digest(events)==SHA256,'candidate file SHA256 differs; refusing replacement data')
    after=events.stat()
    require((before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'event file changed during verification')
    return dict(path=str(events),bytes=before.st_size,mtime_ns=before.st_mtime_ns,sha256=SHA256,
                copy_record=str(ready),copy_record_sha256=digest(ready),original_stage_sha256=STAGE_SHA256)
