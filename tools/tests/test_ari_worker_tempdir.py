"""Container-entry regression tests; no ROOT, Condor, or EIC image needed."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "examples/yall/ari-rf-batch/worker.sh"


class AriWorkerTempdirTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ari-wrapper-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        # Relocate the wrapper exactly as a campaign does, with no nearby helpers.
        self.worker = self.root / "archived worker.sh"
        shutil.copy2(WORKER, self.worker)
        self.eic = self.root / "fake eic-shell"
        # Mimic the real transport's `read` without -r. Reset TMP variables on
        # the container side, so fixing only the host environment cannot pass.
        self.eic.write_text(
            "#!/bin/bash\n"
            "export TMPDIR=/unmounted/condor/host-only TMP=/unmounted/tmp TEMP=/unmounted/temp\n"
            "while read line; do eval \"$line\" || exit $?; done\n"
        )
        self.eic.chmod(0o755)
        self.env = dict(os.environ, _CONDOR_JOB_AD="/fixture/job.ad",
                        TMPDIR="/unmounted/submit-host", TMP="/unmounted/t", TEMP="/unmounted/e")

    def invoke(self, command, **kwargs):
        return subprocess.run(["/bin/bash", str(self.worker), str(self.eic), *command],
                              env=self.env, cwd=self.root, text=True,
                              capture_output=True, **kwargs)

    def probe(self, exit_code=0, *arguments):
        script = (
            "import json,os,pathlib,stat,sys,time; "
            "p=pathlib.Path(os.environ['TMPDIR']); "
            "(p/'payload.tmp').write_text('test'); "
            "print(json.dumps({'tmp':str(p),'temp':os.environ['TEMP'],"
            "'other':os.environ['TMP'],'mode':stat.S_IMODE(p.stat().st_mode),"
            "'worker':os.environ.get('ARI_RF_BATCH_WORKER'),'args':sys.argv[2:]}),flush=True); "
            "time.sleep(0.05); sys.exit(int(sys.argv[1]))"
        )
        return self.invoke([sys.executable, "-c", script, str(exit_code), *arguments])

    def test_container_private_temp_and_cleanup(self):
        result = self.probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["tmp"].startswith("/tmp/ari-rf-worker."))
        self.assertEqual(data["temp"], data["tmp"])
        self.assertEqual(data["other"], data["tmp"])
        self.assertEqual(data["mode"], 0o700)
        self.assertEqual(data["worker"], "1")
        self.assertFalse(Path(data["tmp"]).exists())

    def test_failure_code_and_cleanup(self):
        result = self.probe(37)
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertFalse(Path(json.loads(result.stdout)["tmp"]).exists())

    def test_concurrent_payloads_are_isolated(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.probe(), range(2)))
        self.assertTrue(all(x.returncode == 0 for x in results))
        paths = [json.loads(x.stdout)["tmp"] for x in results]
        self.assertEqual(len(set(paths)), 2)
        self.assertTrue(all(not Path(p).exists() for p in paths))

    def test_argument_transport_still_preserves_quotes(self):
        arguments = ["apostrophe's value", r"literal\backslash", "$(touch SHOULD_NOT_EXIST)", ""]
        result = self.probe(0, *arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["args"], arguments)
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())

    def test_login_host_guard_remains(self):
        self.env.pop("_CONDOR_JOB_AD")
        result = self.probe()
        self.assertEqual(result.returncode, 2)
        self.assertIn("not on the login host", result.stderr)

    def test_container_launcher_failure_propagates(self):
        self.eic.write_text("#!/bin/bash\ncat >/dev/null\nexit 19\n")
        result = self.probe()
        self.assertEqual(result.returncode, 19)
        self.assertEqual(result.stdout, "")

    @unittest.skipUnless(shutil.which("c++"), "C++17 compiler unavailable")
    def test_actual_std_filesystem_failure_and_fix(self):
        source = self.root / "temp_path.cc"
        source.write_text(
            "#include <filesystem>\n#include <iostream>\n"
            "int main(){try{auto p=std::filesystem::temp_directory_path();"
            "std::cout<<p.string()<<'\\n';return 0;}"
            "catch(const std::exception& e){std::cerr<<e.what()<<'\\n';return 1;}}\n"
        )
        binary = self.root / "temp_path"
        subprocess.run([shutil.which("c++"), "-std=c++17", str(source), "-o", str(binary)],
                       check=True, capture_output=True, text=True)
        broken = subprocess.run([str(binary)], env=self.env, capture_output=True, text=True)
        self.assertEqual(broken.returncode, 1)
        self.assertIn("temp_directory_path", broken.stderr)
        fixed = self.invoke([str(binary)])
        self.assertEqual(fixed.returncode, 0, fixed.stderr)
        path = fixed.stdout.strip()
        self.assertTrue(path.startswith("/tmp/ari-rf-worker."))
        self.assertFalse(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
