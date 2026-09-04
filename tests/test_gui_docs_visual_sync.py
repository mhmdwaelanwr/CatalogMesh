import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.gui_docs_visual_sync import image_delta, sync_screenshots


class GuiDocsVisualSyncTests(unittest.TestCase):
    @staticmethod
    def _save(path: Path, *, size=(200, 120), fill=(240, 240, 240)) -> None:
        Image.new("RGB", size, fill).save(path)

    def test_identical_image_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            tracked = root / "tracked"
            candidate.mkdir()
            tracked.mkdir()
            name = "light-01-operation.png"
            self._save(candidate / name)
            self._save(tracked / name)

            result = sync_screenshots(candidate, tracked, threshold=0.005, expected_names=(name,))

            self.assertEqual(result["changed_count"], 0)
            self.assertEqual(result["unchanged_count"], 1)
            self.assertEqual(result["unchanged"][0]["delta"], 0.0)

    def test_tiny_bottom_border_noise_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            tracked = root / "tracked"
            candidate.mkdir()
            tracked.mkdir()
            name = "dark-01-operation.png"
            self._save(candidate / name)
            self._save(tracked / name)

            with Image.open(candidate / name).convert("RGB") as image:
                pixels = image.load()
                for y in range(image.height - 1, image.height):
                    for x in range(70, 111):
                        pixels[x, y] = (228, 228, 228)
                image.save(candidate / name)

            result = sync_screenshots(candidate, tracked, threshold=0.005, expected_names=(name,))

            self.assertEqual(result["changed_count"], 0)
            self.assertLess(result["unchanged"][0]["delta"], 0.005)

    def test_meaningful_visual_change_replaces_tracked_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            tracked = root / "tracked"
            candidate.mkdir()
            tracked.mkdir()
            name = "light-11-environment.png"
            self._save(tracked / name, fill=(245, 245, 245))
            self._save(candidate / name, fill=(225, 225, 225))

            result = sync_screenshots(candidate, tracked, threshold=0.005, expected_names=(name,))

            self.assertEqual(result["changed_count"], 1)
            self.assertGreater(result["changed"][0]["delta"], 0.005)
            with Image.open(candidate / name) as expected, Image.open(tracked / name) as actual:
                self.assertEqual(image_delta(expected, actual), 0.0)

    def test_missing_baseline_is_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            tracked = root / "tracked"
            candidate.mkdir()
            name = "dark-12-about.png"
            self._save(candidate / name)

            result = sync_screenshots(candidate, tracked, threshold=0.005, expected_names=(name,))

            self.assertEqual(result["changed_count"], 1)
            self.assertEqual(result["changed"][0]["reason"], "missing-baseline")
            self.assertTrue((tracked / name).is_file())

    def test_size_change_is_meaningful(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            tracked = root / "tracked"
            candidate.mkdir()
            tracked.mkdir()
            name = "light-02-models.png"
            self._save(candidate / name, size=(201, 120))
            self._save(tracked / name, size=(200, 120))

            result = sync_screenshots(candidate, tracked, threshold=0.005, expected_names=(name,))

            self.assertEqual(result["changed_count"], 1)
            self.assertEqual(result["changed"][0]["delta"], 1.0)

    def test_missing_candidate_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            tracked = root / "tracked"
            candidate.mkdir()
            tracked.mkdir()

            with self.assertRaises(FileNotFoundError):
                sync_screenshots(
                    candidate,
                    tracked,
                    threshold=0.005,
                    expected_names=("light-01-operation.png",),
                )

    def test_invalid_threshold_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            tracked = root / "tracked"
            candidate.mkdir()
            with self.assertRaises(ValueError):
                sync_screenshots(candidate, tracked, threshold=-0.01, expected_names=())


if __name__ == "__main__":
    unittest.main()
