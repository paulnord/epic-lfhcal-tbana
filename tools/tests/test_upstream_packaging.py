"""Offline checks of upstream packaging; no network, builds or submissions."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class UpstreamPackagingTests(unittest.TestCase):
    def test_bootstrap_defaults_to_upstream_main(self):
        text = (ROOT/'tools/bootstrap-yall-integration.sh').read_text()
        self.assertIn('LFHCAL_REPO_URL=${LFHCAL_REPO_URL:-"https://github.com/eic/epic-lfhcal-tbana.git"}', text)
        self.assertIn('LFHCAL_BRANCH=${LFHCAL_BRANCH:-main}', text)
        self.assertNotIn('LFHCAL_BRANCH=${LFHCAL_BRANCH:-yall-integration}', text)

    def test_review_setup_explicitly_overrides_both_repo_and_branch(self):
        text = (ROOT/'examples/yall/SETUP.md').read_text()
        self.assertIn('env LFHCAL_REPO_URL=https://github.com/paulnord/epic-lfhcal-tbana.git LFHCAL_BRANCH=yall-integration-upstream bash', text)
        self.assertIn('After upstream merges this contribution', text)
        self.assertNotIn('raw.githubusercontent.com/paulnord/epic-lfhcal-tbana/yall-integration/', text)

    def test_main_readme_links_to_existing_guides(self):
        text = (ROOT/'README.md').read_text()
        for name in ('QUICKSTART.md', 'SETUP.md', 'README.md'):
            path = 'examples/yall/'+name
            self.assertIn('('+path+')', text)
            self.assertTrue((ROOT/path).is_file())

    def test_existing_installation_does_not_require_bootstrap(self):
        text = (ROOT/'examples/yall/QUICKSTART.md').read_text()
        self.assertIn('do not run the bootstrap just to submit', text)
        self.assertIn('There are\nno build tasks in these example graphs.', text)
        self.assertIn('do **not** source `env.tcsh`', text)


if __name__ == '__main__':
    unittest.main()
