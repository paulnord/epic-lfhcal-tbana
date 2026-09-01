#!/usr/bin/env python3

import importlib.machinery
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
FETCH_TOOL = REPOSITORY / "tools" / "fetch-tb2026-raw"


def load_tool():
    loader = importlib.machinery.SourceFileLoader("fetch_tb2026_raw", str(FETCH_TOOL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


class FetchTB2026RawTests(unittest.TestCase):
    def test_run_numbers_and_ranges_are_expanded_and_deduplicated(self):
        tool = load_tool()
        self.assertEqual(tool.parse_runs(["137", "138-140", "139", "153"]), [137, 138, 139, 140, 153])

    def test_dry_run_builds_new_jlab_download_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary) / "raw data"
            result = subprocess.run(
                [
                    sys.executable,
                    str(FETCH_TOOL),
                    "--dry-run",
                    "--destination",
                    str(destination),
                    "137",
                    "138-139",
                    "153",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(all("--continue" not in line for line in lines))
        self.assertIn("2026_SPSH2/raw/Run137.h2g", lines[0])
        self.assertIn("Run153.h2g", lines[-1])

    def test_existing_destination_is_resumed(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary)
            (destination / "Run137.h2g").touch()
            command = tool.copy_command(
                "xrdcp",
                tool.DEFAULT_SOURCE,
                destination,
                137,
                force=False,
            )

        self.assertEqual(command[1], "--continue")

    def test_force_replaces_existing_destination(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary)
            command = tool.copy_command(
                "xrdcp",
                tool.DEFAULT_SOURCE,
                destination,
                137,
                force=True,
            )

        self.assertEqual(command[1], "--force")

    def test_invalid_descending_range_is_rejected(self):
        result = subprocess.run(
            [sys.executable, str(FETCH_TOOL), "--dry-run", "149-138"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("run range must be ascending", result.stderr)


if __name__ == "__main__":
    unittest.main()
