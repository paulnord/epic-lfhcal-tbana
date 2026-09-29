"""Offline checks for running local Yall from the checkout inside eic-shell."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENV_EIC = ROOT / "examples/yall/lfhcal-simple/env-eic.sh"
BOOTSTRAP = ROOT / "tools/bootstrap-yall-integration.sh"


class EicYallSourceTest(unittest.TestCase):
    def test_env_eic_shell_syntax(self):
        subprocess.run(["bash", "-n", str(ENV_EIC)], check=True)

    def test_env_eic_uses_checkout_not_user_site_install(self):
        text = ENV_EIC.read_text()
        self.assertIn('export PYTHONPATH="$_yall_src${PYTHONPATH:+:$PYTHONPATH}"', text)
        self.assertIn('python3 -m yall_run.cli "$@"', text)
        self.assertNotIn('site --user-base', text)
        self.assertNotIn('python3 -m pip install', text)

    def test_bootstrap_has_one_host_install_and_container_source_smoke_test(self):
        text = BOOTSTRAP.read_text()
        self.assertEqual(text.count('python3 -m pip install --user -e "$YALL_DIR"'), 1)
        self.assertIn('source ./env-eic.sh >/dev/null && yall-run --version', text)
        self.assertNotIn('run-in-eic-shell.sh" "$EIC_SHELL" \\\n    python3 -m pip install', text)


if __name__ == "__main__":
    unittest.main()
