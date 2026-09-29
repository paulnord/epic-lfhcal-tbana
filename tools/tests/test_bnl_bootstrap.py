"""Offline bootstrap tests. No BNL access, downloads, builds or submissions.

Run: python3 -m unittest discover -s tools/tests -v
Tests of sourced setup use real tcsh when it is installed; otherwise skip.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
BOOTSTRAP = TOOLS / "bootstrap-yall-integration.sh"
TCSH = shutil.which("tcsh")


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\nset -eu\n" + text, encoding="utf-8")
    path.chmod(0o755)


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "my-workspace"
        self.workspace.mkdir()
        self.bin = self.root / "host-bin"
        self.bin.mkdir()
        self.userbase = self.root / "user-install"
        self.log = self.root / "calls.log"
        self.repo = self.workspace / "epic-lfhcal-tbana"
        for checkout in (self.repo, self.workspace / "yall-run"):
            (checkout / ".git").mkdir(parents=True)
        executable(self.bin / "git", 'printf "git %s\\n" "$*" >> "$TEST_LOG"\n')
        executable(self.bin / "curl", 'echo "unexpected download" >&2; exit 99\n')
        executable(self.bin / "tcsh", 'printf "tcsh %s\\n" "$*" >> "$TEST_LOG"\nexit "${TEST_TCSH_RC:-0}"\n')
        executable(self.bin / "python3", '''printf "python3 %s\\n" "$*" >> "$TEST_LOG"
if [[ "$*" == "-m site --user-base" ]]; then
    echo "$TEST_USERBASE"
elif [[ "$*" != "-m pip install --user -e "* ]]; then
    echo "unexpected python invocation: $*" >&2
    exit 99
fi
''')
        for cmd in ("condor_submit", "condor_submit_dag"):
            executable(self.bin / cmd, 'echo "unexpected submission" >&2; exit 99\n')
        executable(self.userbase / "bin/yall-run", '[[ "$*" == "--help" ]]\n')
        executable(self.workspace / "eic-shell", 'exit 0\n')
        executable(self.repo / "tools/run-in-eic-shell.sh", '''printf "wrapper %s\\n" "$*" >> "$TEST_LOG"
[[ "$1" == "$TEST_WORKSPACE/eic-shell" ]]
shift
if [[ "$1" == cmake && "$2" == --build ]]; then
    mkdir -p "$3"
    for exe in Convert DataPrep; do
        printf '#!/bin/sh\\nexit 0\\n' > "$3/$exe"
        chmod +x "$3/$exe"
    done
elif [[ "$*" == "root-config --version" ]]; then
    echo "mock-ROOT"
fi
''')
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("LFHCAL_", "YALL_", "EIC_"))}
        self.env.update(PATH=f"{self.bin}:{os.environ['PATH']}",
                        TEST_LOG=str(self.log), TEST_USERBASE=str(self.userbase),
                        TEST_WORKSPACE=str(self.workspace))

    def run_install(self):
        return subprocess.run(["bash", str(BOOTSTRAP)], cwd=self.workspace,
                              env=self.env, capture_output=True, text=True)

    def install_ok(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_syntax(self):
        subprocess.run(["bash", "-n", str(BOOTSTRAP)], check=True)

    def test_tcsh_only_generation_and_bnl_defaults(self):
        self.install_ok()
        site = (self.workspace / "site-env.tcsh").read_text()
        activate = (self.workspace / "activate.tcsh").read_text()
        self.assertIn('/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata', site)
        self.assertIn('/gpfs01/star/scratch/`id -un`/lfhcal', site)
        self.assertIn('mkdir -p "$LFHCAL_WORK/campaigns"', activate)
        self.assertIn('! -r "$LFHCAL_DATA"', activate)
        self.assertNotIn('mkdir -p "$LFHCAL_DATA"', activate)
        self.assertFalse((self.workspace / "activate.sh").exists())
        self.assertFalse((self.workspace / "site-env.sh").exists())
        self.assertFalse((self.workspace / "data").exists())
        self.assertFalse((self.workspace / "work").exists())
        self.assertFalse((self.workspace / ".venv-yall").exists())

    def test_existing_settings_and_old_generated_files_preserved(self):
        custom = 'setenv LFHCAL_DATA /existing/raw\nsetenv LFHCAL_WORK /existing/work\n'
        (self.workspace / "site-env.tcsh").write_text(custom)
        (self.workspace / "site-env.sh").write_text("# user edits, preserve\n")
        self.install_ok()
        self.assertEqual((self.workspace / "site-env.tcsh").read_text(), custom)
        self.assertEqual((self.workspace / "site-env.sh").read_text(), "# user edits, preserve\n")

    def test_host_user_install_container_build_no_submission(self):
        self.install_ok()
        log = self.log.read_text()
        self.assertIn(f'python3 -m pip install --user -e {self.workspace}/yall-run', log)
        self.assertIn('submodule update --init --recursive', log)
        self.assertIn('cmake --build', log)
        self.assertNotIn('venv', log)
        self.assertNotIn('pip install --upgrade', log)
        self.assertNotIn('condor_submit', log)

    def test_scratch_setup_failure_stops_before_install_or_build(self):
        self.env['TEST_TCSH_RC'] = '1'
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('pip install', self.log.read_text())
        self.assertNotIn('cmake', self.log.read_text())

    def test_current_folder_wins_over_old_environment(self):
        self.env['LFHCAL_HOME'] = str(self.root / 'old-install')
        self.install_ok()
        text = (self.workspace / "activate.tcsh").read_text()
        self.assertIn(f'setenv LFHCAL_HOME "{self.workspace}"', text)
        self.assertFalse((self.root / 'old-install').exists())

    def test_parent_directories_created_by_generated_mkdir(self):
        # Execute the generated mkdir line itself. This is not a tcsh test.
        self.install_ok()
        activation = (self.workspace / 'activate.tcsh').read_text()
        mkdir = next(line.strip() for line in activation.splitlines()
                     if line.strip().startswith('mkdir -p '))
        scratch = self.root / 'scratch' / 'new-user' / 'lfhcal'
        env = dict(self.env, LFHCAL_WORK=str(scratch))
        subprocess.run(['bash', '-c', mkdir], env=env, check=True)
        self.assertTrue((scratch / 'campaigns').is_dir())
        marker = scratch / 'keep-me'
        marker.write_text('earlier output')
        subprocess.run(['bash', '-c', mkdir], env=env, check=True)
        self.assertEqual(marker.read_text(), 'earlier output')

    @unittest.skipUnless(TCSH, 'tcsh is not installed')
    def test_real_tcsh_source_creates_scratch_and_leaves_input_unchanged(self):
        self.install_ok()
        raw = self.root / 'raw'
        raw.mkdir()
        (raw / 'Run296.h2g').write_text('unchanged')
        scratch = self.root / 'scratch' / 'new-user' / 'lfhcal'
        env = dict(self.env, LFHCAL_DATA=str(raw), LFHCAL_WORK=str(scratch))
        result = subprocess.run([TCSH, '-f', str(self.workspace / 'activate.tcsh')],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((scratch / 'campaigns').is_dir())
        self.assertEqual([p.name for p in raw.iterdir()], ['Run296.h2g'])

    @unittest.skipUnless(TCSH, 'tcsh is not installed')
    def test_real_tcsh_work_failure_returns_error(self):
        self.install_ok()
        blocker = self.root / 'not-a-directory'
        blocker.write_text('keep')
        env = dict(self.env, LFHCAL_DATA=str(self.root),
                   LFHCAL_WORK=str(blocker / 'lfhcal'))
        result = subprocess.run([TCSH, '-f', str(self.workspace / 'activate.tcsh')],
                                env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(blocker.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
