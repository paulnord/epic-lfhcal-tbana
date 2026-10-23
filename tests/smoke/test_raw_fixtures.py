"""Offline fixture-integrity checks only; passing is not decoder validation."""
import hashlib
import json
import unittest

from caen_fixture import FIXTURES, malformed_variants, parse_capture


class RawFixtureTests(unittest.TestCase):
    def test_hashes_sizes_and_complete_records(self):
        manifest = json.loads((FIXTURES / "manifest.json").read_text())
        self.assertEqual(len(manifest["fixtures"]), 2)
        for fixture in manifest["fixtures"]:
            with self.subTest(file=fixture["file"]):
                raw = (FIXTURES / fixture["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture["fixture_sha256"])
                self.assertEqual(len(raw), fixture["fixture_size_bytes"])
                self.assertEqual(len(parse_capture(raw)), fixture["fixture_complete_records"])
                self.assertTrue(raw.endswith(b"\r\n"))
                self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))

    def test_run34_record_values(self):
        events = parse_capture((FIXTURES / "Run34_first16.txt").read_bytes())
        self.assertEqual(len(events), 16)
        self.assertEqual(events[0], {"id": 0, "time": 0.088,
                                    "tiles": [[0, 55, 0], [1, 62, 64], [2, 60, 67]]})
        self.assertEqual(events[1]["id"], 52)

    def test_run36_is_complete_despite_acquisition_quality(self):
        events = parse_capture((FIXTURES / "Run36_list.txt").read_bytes())
        self.assertEqual(len(events), 533)
        resets = [i for i in range(1, len(events)) if events[i]["id"] < events[i-1]["id"]]
        self.assertEqual(resets, [511])
        self.assertEqual([events[i]["id"] for i in (0, 510, 511, 532)],
                         [17261297, 17320577, 0, 21])
        self.assertTrue(all(events[i]["time"] > events[i-1]["time"]
                            for i in range(1, len(events))))

    def test_controlled_corruptions_are_deterministic_and_invalid(self):
        raw = (FIXTURES / "Run34_first16.txt").read_bytes()
        variants = malformed_variants(raw)
        self.assertEqual(variants, malformed_variants(raw))
        self.assertEqual(set(variants), {"unsupported_format", "short_header",
                                         "truncated_hit", "nonnumeric_adc"})
        for name, variant in variants.items():
            with self.subTest(variant=name):
                self.assertNotIn(b"\r", variant)
                with self.assertRaises(ValueError):
                    parse_capture(variant)


if __name__ == "__main__":
    unittest.main()
