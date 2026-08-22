import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from unittest.mock import MagicMock, patch

from sorter_core import (
    Photo, call_gemini, check_internet, choose_operation, connect_db, load_api_keys,
    format_duration, install_requirements, internet_quality, load_env_file,
    merge_observations, missing_requirements, normalize_response, progress_count,
    select_photo_sample, write_status_files,
)


class MergeTests(unittest.TestCase):
    def test_normalize_accepts_top_level_list_from_newer_gemini_models(self):
        photos = [Photo(Path("one.jpg"), datetime(2026, 8, 22))]
        raw = '[{"filename":"one.jpg","category":"other","confidence":0.9}]'
        result = normalize_response(raw, photos)
        self.assertEqual(result["items"][0]["filename"], "one.jpg")

    def test_normalize_still_accepts_items_object(self):
        photos = [Photo(Path("one.jpg"), datetime(2026, 8, 22))]
        raw = '{"items":[{"filename":"one.jpg","category":"other","confidence":0.9}]}'
        result = normalize_response(raw, photos)
        self.assertEqual(result["items"][0]["filename"], "one.jpg")

    def test_overlap_prefers_higher_confidence(self):
        base = datetime(2026, 8, 20, 10, 0, 0)
        with tempfile.TemporaryDirectory() as directory:
            photos = [Photo(Path(directory) / f"{i}.jpg", base + timedelta(seconds=i)) for i in range(3)]
            responses = [
                {"items": [
                    {"filename": "0.jpg", "confidence": .8, "same_product_as_previous": False},
                    {"filename": "1.jpg", "confidence": .6, "same_product_as_previous": True},
                ]},
                {"items": [
                    {"filename": "1.jpg", "confidence": .9, "same_product_as_previous": False},
                    {"filename": "2.jpg", "confidence": .8, "same_product_as_previous": True},
                ]},
            ]
            merged = merge_observations(photos, responses)
            self.assertEqual(len(merged), 3)
            self.assertEqual(merged[1]["confidence"], .9)
            self.assertTrue(merged[1]["same_product_as_previous"])


class ApiKeyTests(unittest.TestCase):
    @patch.dict("os.environ", {"EXISTING_SETTING": "from-terminal"}, clear=True)
    def test_env_file_loads_values_without_overriding_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "GEMINI_API_KEY_1='from-file'\nEXISTING_SETTING='from-file'\n",
                encoding="utf-8",
            )
            self.assertTrue(load_env_file(env_file))
            self.assertEqual(os.environ["GEMINI_API_KEY_1"], "from-file")
            self.assertEqual(os.environ["EXISTING_SETTING"], "from-terminal")

    @patch.dict("os.environ", {
        "GEMINI_API_KEY_1": "first", "GEMINI_API_KEY_2": "second",
        "GEMINI_API_KEY_3": "third", "GEMINI_API_KEY_4": "fourth",
        "GEMINI_API_KEY": "legacy",
    }, clear=True)
    def test_loads_at_most_four_numbered_keys(self):
        self.assertEqual(load_api_keys(), ["first", "second", "third", "fourth"])

    @patch.dict("os.environ", {"GEMINI_API_KEY": "legacy"}, clear=True)
    def test_legacy_single_key_still_works(self):
        self.assertEqual(load_api_keys(), ["legacy"])


class RequirementsTests(unittest.TestCase):
    @patch("sorter_core.importlib.util.find_spec")
    def test_missing_requirements_are_reported(self, mocked_find_spec):
        mocked_find_spec.side_effect = lambda name: None if name == "PIL" else object()
        self.assertEqual(missing_requirements(), ["Pillow"])

    @patch("sorter_core.subprocess.run")
    def test_installer_uses_current_python_and_requirements_file(self, mocked_run):
        mocked_run.return_value = SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as directory:
            requirements = Path(directory) / "requirements.txt"
            requirements.write_text("Pillow\n", encoding="utf-8")
            self.assertTrue(install_requirements(requirements))
            command = mocked_run.call_args.args[0]
            self.assertEqual(command[:4], [sys.executable, "-m", "pip", "install"])
            self.assertEqual(command[-1], str(requirements))

    def test_clear_error_after_every_key_exhausts_quota(self):
        class Models:
            def generate_content(self, **kwargs):
                raise RuntimeError("429 RESOURCE_EXHAUSTED")

        class Client:
            models = Models()

        class Pool:
            clients = [Client(), Client(), Client(), Client()]
            index = 0

            @property
            def client(self):
                return self.clients[self.index]

            def rotate(self):
                self.index = (self.index + 1) % len(self.clients)
                return True

        fake_types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
        with patch("sorter_core.types", fake_types), \
                patch("sorter_core.getpass.getpass", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "No new API key was entered"):
                call_gemini(Pool(), "test-model", [], "", max_retries=0)

    def test_new_interactive_key_retries_current_batch(self):
        class Models:
            def __init__(self, exhausted=True):
                self.exhausted = exhausted

            def generate_content(self, **kwargs):
                if self.exhausted:
                    raise RuntimeError("429 RESOURCE_EXHAUSTED")
                return SimpleNamespace(text='{"items":[]}')

        class Client:
            def __init__(self, exhausted=True):
                self.models = Models(exhausted)

        class Pool:
            clients = [Client(), Client(), Client(), Client()]
            index = 0

            @property
            def client(self):
                return self.clients[self.index]

            def rotate(self):
                self.index = (self.index + 1) % len(self.clients)
                return True

            def add_key(self, key):
                self.clients.append(Client(exhausted=False))
                self.index = len(self.clients) - 1

        fake_types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
        with patch("sorter_core.types", fake_types), \
                patch("sorter_core.getpass.getpass", return_value="new-secret-key"):
            self.assertEqual(
                call_gemini(Pool(), "test-model", [], "", max_retries=0),
                {"items": []},
            )


class ProgressTests(unittest.TestCase):
    @patch("builtins.input", return_value="2")
    def test_quick_sample_uses_configured_limit(self, mocked_input):
        photos = [Photo(Path(f"{i}.jpg"), datetime.now()) for i in range(100)]
        self.assertEqual(len(select_photo_sample(photos, 25)), 25)

    @patch("builtins.input", side_effect=["3", "7"])
    def test_custom_sample_count(self, mocked_input):
        photos = [Photo(Path(f"{i}.jpg"), datetime.now()) for i in range(10)]
        self.assertEqual(len(select_photo_sample(photos, None)), 7)

    def test_duration_format_for_countdown(self):
        self.assertEqual(format_duration(65), "01:05")
        self.assertEqual(format_duration(3661), "01:01:01")

    def test_progress_count_uses_cached_filenames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photos = [Photo(root / f"{i}.jpg", datetime.now()) for i in range(3)]
            db = connect_db(root / "progress.sqlite3")
            db.execute(
                "INSERT INTO batches VALUES (?, ?, ?, ?, ?)",
                ("key", "model", "[]", '{"items":[{"filename":"0.jpg"},{"filename":"1.jpg"}]}',
                 datetime.now().isoformat()),
            )
            db.commit()
            self.assertEqual(progress_count(db, photos), 2)

    def test_status_files_list_completed_and_pending_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photos = [Photo(root / f"{i}.jpg", datetime.now()) for i in range(3)]
            db = connect_db(root / "progress.sqlite3")
            db.execute(
                "INSERT INTO batches VALUES (?, ?, ?, ?, ?)",
                ("key", "model", "[]", '{"items":[{"filename":"0.jpg"}]}',
                 datetime.now().isoformat()),
            )
            db.commit()
            write_status_files(root, photos, db)
            self.assertEqual((root / "completed_files.txt").read_text().strip(), "0.jpg")
            self.assertEqual(
                (root / "pending_files.txt").read_text().splitlines(),
                ["1.jpg", "2.jpg"],
            )
            status_csv = (root / "processing_status.csv").read_text(encoding="utf-8-sig")
            self.assertIn("0.jpg", status_csv)
            self.assertIn("completed", status_csv)
            self.assertIn("pending", status_csv)

    @patch("builtins.input", return_value="2")
    def test_new_operation_gets_separate_folder(self, mocked_input):
        output = Path("/tmp/Sorted_Products")
        action, selected = choose_operation(output, 10, 20)
        self.assertEqual(action, "new")
        self.assertNotEqual(selected, output)
        self.assertTrue(selected.name.startswith("Sorted_Products_New_"))


class InternetTests(unittest.TestCase):
    def test_quality_levels_use_response_latency(self):
        self.assertEqual(internet_quality(100), "excellent")
        self.assertEqual(internet_quality(450), "good")
        self.assertEqual(internet_quality(900), "fair")
        self.assertEqual(internet_quality(2000), "weak")

    @patch("sorter_core.time.perf_counter", side_effect=[10.0, 10.2])
    @patch("sorter_core.urllib.request.urlopen")
    def test_connected_check_reports_latency(self, mocked_urlopen, mocked_clock):
        response = MagicMock()
        response.__enter__.return_value = response
        mocked_urlopen.return_value = response
        connected, latency, quality = check_internet()
        self.assertTrue(connected)
        self.assertAlmostEqual(latency, 200.0)
        self.assertEqual(quality, "excellent")

    @patch("sorter_core.urllib.request.urlopen", side_effect=OSError("offline"))
    def test_offline_check_does_not_crash(self, mocked_urlopen):
        self.assertEqual(check_internet(), (False, None, "offline"))


if __name__ == "__main__":
    unittest.main()
