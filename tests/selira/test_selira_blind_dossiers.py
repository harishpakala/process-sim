"""Tests for evidence-only blind dossier export."""

# Created: 2026-10-30
# Author: Harish
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_selira_blind_dossiers import generate


class BlindDossierTests(unittest.TestCase):
    def test_review_package_has_ten_cases_thirty_blank_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            mapping = generate({"status": "FOCUSED_RELATIONSHIP_DISCOVERY_ONLY",
                                "facts": []}, directory, seed=2027)
            self.assertEqual(len(mapping), 10)
            self.assertEqual(set(mapping.values()),
                             {"E" + str(n) for n in range(1, 11)})
            with (directory / "blank-review-form.csv").open(
                    newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 30)
            self.assertEqual({row["referenceStatus"] for row in rows}, {""})
            for path in directory.glob("D-*.json"):
                data = path.read_text(encoding="utf-8")
                self.assertNotIn("seliraSource", data)
                self.assertNotIn("shaclConforms", data)
                self.assertNotIn("referenceSourceStatus", data)

    def test_manifest_hashes_match(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            generate({"facts": []}, directory)
            manifest = json.loads((directory / "manifest.json").read_text())
            for row in manifest:
                self.assertEqual(hashlib.sha256(
                    (directory / row["filename"]).read_bytes()).hexdigest(),
                    row["sha256"])


if __name__ == "__main__":
    unittest.main()
