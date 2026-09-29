"""ROOT-free tests of additional-set staging. Not calibration validation."""
import ast
from pathlib import Path
import tempfile
import unittest
import extend_adaptive_fulltests as e


def recipe(code='g1', mapping='1', bad='G', toa='G', pedestal=485, muons=(484,486)):
    return f'''campaign example
@set SET FullSet{code[0].upper()}_{code[1:]}
@set MAPPING ../../../configs/TB2026/mapping_HGCROC_SPSH2TB_sumV{mapping}_default.csv
@set BAD_CHANNELS ../../../configs/TB2026/badChannel_HGCROC_SPSTB2026_FullSet{bad}.txt
@set TOA ../../../configs/TB2026/ToAOffsets_TBSPS2026_FullSet{toa}.csv
@table runs type run:
    pedestal {pedestal}
'''+''.join(f'    muon {r}\n' for r in muons)+'''\n%cpus 1
prepare:
    echo start
'''


# The exact anchors and relevant source structure from the pinned launcher;
# runtime also checks the complete original Git blob fingerprint before editing.
FIXTURE = '''SPECS = {
    'b2': {'fullset':'FullSetB_2'},
    'e1': {'fullset':'FullSetE_1'},
    'e3': {'fullset':'FullSetE_3'},
}
MODELS = ('legacy', 'adaptive')
STAGES = ('mip', 'select', 'refine1', 'refine2', 'refine3', 'refine4', 'refine5')
def config(cfg,spec):
    return (cfg/'mapping_HGCROC_SPSH2TB_sumV2_default.csv',
            cfg/'badChannel_HGCROC_SPSTB2026_FullSetA-F.txt',
            cfg/f'ToAOffsets_TBSPS2026_FullSet{spec["toa"]}.csv')
def find_pedestal(root,spec):
    if True:
        ped = root/'pedestal'/'rawHGCROC_wPed.root'
        return ped

def summary():
    return dict(scope='3 datasets, two full MIP chains each, 6 fit passes per chain')
def manifest():
    return dict(base_commit=BASE,kit_commit=KIT,decoder_commit=DECODER,
                inputs=inputs)
def yallfile():
    return 'campaign lfhcal-minimal-adaptive-fullchains'
def prepare():
    print('51 tasks: 2 builds + 3 shared inputs + 42 chain stages + 3 comparisons + summary.')
'''


class ExtensionTests(unittest.TestCase):
    def old(self):
        return dict(base_commit=e.BASE,kit_commit=e.KIT,specs={c:{} for c in ('b2','e1','e3')})

    def test_remaining_eleven_without_duplicates(self):
        self.assertEqual(e.remaining_sets(self.old()),
                         ('b1','c1','c2','c3','d1','d2','e2','f1','f2','g1','g2'))
        self.assertEqual(3+16*len(e.remaining_sets(self.old())),179)

    def test_reject_already_scheduled_and_bad_selection(self):
        for codes in (['e1'],['b1','b1'],['z9']):
            with self.subTest(codes=codes),self.assertRaises(ValueError):
                e.remaining_sets(self.old(),codes)
        self.assertEqual(e.remaining_sets(self.old(),['g2']),('g2',))

    def test_reject_different_fitter_versions(self):
        old=self.old();old['kit_commit']='different'
        with self.assertRaises(ValueError):e.remaining_sets(old)

    def test_read_g_mapping_and_bad_channel_map(self):
        spec=e.parse_recipe('g1',recipe())
        self.assertEqual(spec['pedestal'],485)
        self.assertEqual(spec['muons'],[484,486])
        self.assertEqual(spec['mapping'],'mapping_HGCROC_SPSH2TB_sumV1_default.csv')
        self.assertEqual(spec['bad_channels'],'badChannel_HGCROC_SPSTB2026_FullSetG.txt')

    def test_toa_exceptions_are_explicit_not_inferred(self):
        c=e.parse_recipe('c3',recipe('c3','2','A-F','C_2',278,(279,280)))
        d=e.parse_recipe('e3',recipe('e3','2','A-F','F',471,(473,474)))
        self.assertEqual(c['toa'],'C_2');self.assertEqual(d['toa'],'F')

    def test_inline_config_form_and_muons_before_pedestal(self):
        text=recipe('f1','2','A-F','F',431,(426,427))
        text=text.replace('@set MAPPING','    @input mapping')
        text=text.replace('    pedestal 431\n','')
        text=text.replace('\n%cpus','    pedestal 431\n\n%cpus')
        self.assertEqual(e.parse_recipe('f1',text)['pedestal'],431)

    def test_ambiguous_and_missing_configs_fail(self):
        for text in (recipe()+'\n@set OTHER ToAOffsets_TBSPS2026_FullSetF.csv\n',
                     recipe().replace('mapping_HGCROC_SPSH2TB_sumV1_default.csv','unknown')):
            with self.assertRaises(ValueError):e.parse_recipe('g1',text)

    def test_comments_do_not_change_settings(self):
        text=recipe()+'\n# old ToAOffsets_TBSPS2026_FullSetF.csv\n'
        self.assertEqual(e.parse_recipe('g1',text)['toa'],'G')

    def test_multiple_pedestals_and_duplicate_runs_fail(self):
        for text in (recipe().replace('    pedestal 485','    pedestal 485\n    pedestal 529'),
                     recipe().replace('    muon 484','    muon 484\n    muon 484')):
            with self.assertRaises(ValueError):e.parse_recipe('g1',text)

    def test_transform_preserves_stages_and_routes_configs(self):
        specs={c:e.parse_recipe('g1',recipe()) for c in e.remaining_sets(self.old())}
        result=e.expand_launcher(FIXTURE,specs,{'previous_campaign_root':'/old'})
        namespace={};exec(result,namespace)
        self.assertEqual(tuple(namespace['SPECS']),tuple(sorted(specs)))
        self.assertEqual(namespace['STAGES'],('mip','select','refine1','refine2','refine3','refine4','refine5'))
        self.assertIn('179 tasks:',result)
        self.assertIn("dict(extension=EXTENSION,base_commit=BASE",result)
        cfg=namespace['config'](Path('/cfg'),e.parse_recipe('g1',recipe()))
        self.assertEqual(cfg[0].name,'mapping_HGCROC_SPSH2TB_sumV1_default.csv')
        self.assertEqual(cfg[1].name,'badChannel_HGCROC_SPSTB2026_FullSetG.txt')
        with self.assertRaises(ValueError):e.expand_launcher(result,specs,{})

    def test_supports_numbered_pedestal_without_overwriting_files(self):
        result=e.expand_launcher(FIXTURE,{'f1':e.parse_recipe('f1',recipe('f1','2','A-F','F',431))},{})
        namespace={};exec(result,namespace)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'pedestal';p.mkdir()
            numbered=p/'rawHGCROC_wPed_431.root';numbered.write_text('numbered')
            self.assertEqual(namespace['find_pedestal'](root,{'pedestal':431}),numbered)
            plain=p/'rawHGCROC_wPed.root';plain.write_text('plain')
            self.assertEqual(namespace['find_pedestal'](root,{'pedestal':431}),plain)

    def test_fresh_destination_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);previous=root/'old';repo=root/'repo'
            previous.mkdir();repo.mkdir()
            e.safe_new_destination(root/'new',previous,repo)
            for bad in (previous,previous/'new',repo/'new',root):
                with self.assertRaises(ValueError):e.safe_new_destination(bad,previous,repo)

    def test_source_anchors_refuse_unexpected_content(self):
        with self.assertRaises(ValueError):e.once('x x','x','y')
        with self.assertRaises(ValueError):e.once('z','x','y')
        self.assertEqual(e.blob_sha(b''),'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')


if __name__=='__main__':unittest.main()
