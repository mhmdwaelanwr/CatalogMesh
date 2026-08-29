from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "generate_local_evidence_fixture.py"


class LocalEvidenceFixtureTests(unittest.TestCase):
    def test_fixture_generator_creates_valid_jpeg_labels_without_optional_backends(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "fixture"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output), "--count", "4"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            photos = sorted(output.glob("*.jpg"))
            self.assertEqual(len(photos), 4)
            for photo in photos:
                with Image.open(photo) as image:
                    self.assertEqual(image.format, "JPEG")
                    self.assertEqual(image.size, (900, 650))
                    image.verify()


if __name__ == "__main__":
    unittest.main()
