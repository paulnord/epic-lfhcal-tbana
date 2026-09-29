"""Offline onboarding-doc and data-path regressions; no BNL/ROOT/submission."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = '/gpfs01/star/pwg/pnord/eic/2026TBdata/raw'


class OnboardingTests(unittest.TestCase):
    def test_tldr_link_is_at_top_of_setup(self):
        lines = (ROOT/'examples/yall/SETUP.md').read_text().splitlines()
        self.assertIn('(SETUP_TLDR.md)', '\n'.join(lines[:6]))
        self.assertTrue((ROOT/'examples/yall/SETUP_TLDR.md').is_file())

    def test_tldr_leads_with_fresh_install_and_links_existing_install(self):
        text = (ROOT/'examples/yall/SETUP_TLDR.md').read_text()
        self.assertIn('## New installation: start here', text)
        self.assertIn('curl -fL https://raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration-upstream/tools/bootstrap-yall-integration.sh', text)
        self.assertIn('LFHCAL_BRANCH=yall-integration-upstream', text)
        self.assertIn('(EXISTING_INSTALL.md)', text)
        self.assertIn('9 completed tasks', text)
        self.assertIn('%preflight', text)
        self.assertIn('-j 1', text)

    def test_defaults_match_and_do_not_canonicalize_mount_alias(self):
        for relative in ('tools/bootstrap-yall-integration.sh',
                         'examples/yall/lfhcal-simple/env-eic.sh'):
            text = (ROOT/relative).read_text()
            self.assertIn(DEFAULT_DATA, text)
            self.assertNotIn('/gpfs/mnt', text)

    def test_guides_name_the_raw_subdirectory(self):
        for name in ('SETUP.md', 'SETUP_TLDR.md'):
            text = (ROOT/'examples/yall'/name).read_text()
            self.assertIn(DEFAULT_DATA, text)

    def source_eic_environment(self, raw_override=None):
        with tempfile.TemporaryDirectory() as d:
            workspace = Path(d)
            example = workspace/'epic-lfhcal-tbana/examples/yall/lfhcal-simple'
            example.mkdir(parents=True)
            script = example/'env-eic.sh'
            shutil.copy2(ROOT/'examples/yall/lfhcal-simple/env-eic.sh', script)
            package = workspace/'yall-run/src/yall_run'
            package.mkdir(parents=True)
            (package/'__init__.py').write_text('')
            (package/'cli.py').write_text('print("test-yall")\n')
            env = {k:v for k,v in os.environ.items()
                   if not k.startswith(('LFHCAL_', 'YALL_', 'EIC_', 'PYTHONPATH'))}
            env['LFHCAL_WORK'] = str(workspace/'work')
            if raw_override is not None:
                env['LFHCAL_DATA'] = raw_override
            result = subprocess.run(['bash', '-c',
                'source "$1" || exit $?; printf "SELECTED_RAW=%s\\n" "$LFHCAL_DATA"',
                'source-test', str(script)], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertTrue((workspace/'work/campaigns').is_dir())
            return next(line.split('=',1)[1] for line in result.stdout.splitlines()
                        if line.startswith('SELECTED_RAW='))

    def test_eic_default_uses_short_mount_path(self):
        self.assertEqual(self.source_eic_environment(), DEFAULT_DATA)

    def test_eic_preserves_explicit_user_data_path(self):
        self.assertEqual(self.source_eic_environment('/custom/raw-input'), '/custom/raw-input')

    def test_documented_one_time_fix_preserves_other_settings_and_backup(self):
        text = (ROOT/'examples/yall/SETUP.md').read_text()
        command = next(line for line in text.splitlines() if line.startswith('sed -i.bnl-raw-backup '))
        parent = str(Path(DEFAULT_DATA).parent)
        variants = (parent, '/gpfs/mnt'+parent, DEFAULT_DATA,
                    '/gpfs/mnt'+DEFAULT_DATA, '/custom/raw-input', parent+'/converted')
        for old in variants:
            with self.subTest(old=old), tempfile.TemporaryDirectory() as d:
                original = ('if (! $?LFHCAL_DATA) setenv LFHCAL_DATA "'+old+'"\n'
                            'setenv LFHCAL_WORK "/my/existing/output"\n# keep this comment\n')
                site = Path(d)/'site-env.tcsh'
                site.write_text(original)
                env = dict(os.environ, LFHCAL_HOME=d)
                subprocess.run(['bash','-c',command],env=env,check=True)
                expected = original if old in variants[-2:] else original.replace(old,DEFAULT_DATA)
                self.assertEqual(site.read_text(),expected)
                self.assertEqual(Path(str(site)+'.bnl-raw-backup').read_text(),original)
                self.assertNotIn('/raw/raw',site.read_text())


if __name__ == '__main__':
    unittest.main()
