import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_photo_sorter import performance_pipeline
from ai_product_photo_sorter.performance_gui import prepare_performance_environment_fields


class _ImageContext:
    def __init__(self, size):
        self.size = size

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _ImageAPI:
    def __init__(self, size):
        self.size = size

    def open(self, path):
        return _ImageContext(self.size)


class PerformancePipelineTests(unittest.TestCase):
    def test_worker_configuration_supports_auto_off_and_explicit_values(self):
        with patch.dict(os.environ, {"PRODUCT_SORTER_PREPROCESS_WORKERS": "off"}, clear=False):
            self.assertEqual(0, performance_pipeline._configured_workers())
        with patch.dict(os.environ, {"PRODUCT_SORTER_PREPROCESS_WORKERS": "3"}, clear=False):
            self.assertEqual(3, performance_pipeline._configured_workers())
        with patch.dict(os.environ, {"PRODUCT_SORTER_PREPROCESS_WORKERS": "99"}, clear=False):
            with self.assertRaises(ValueError):
                performance_pipeline._configured_workers()

    def test_memory_safety_caps_large_images_to_one_worker(self):
        photos = [SimpleNamespace(path=Path("a.jpg")), SimpleNamespace(path=Path("b.jpg"))]
        module = SimpleNamespace(Image=_ImageAPI((10000, 10000)))
        with patch.dict(
            os.environ,
            {"PRODUCT_SORTER_PREPROCESS_MEMORY_MB": "512"},
            clear=False,
        ):
            workers = performance_pipeline._memory_safe_workers(module, photos, 4)
        self.assertEqual(1, workers)

    def test_preprocessor_warms_cache_once_per_identical_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.jpg"
            second = root / "b.jpg"
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            calls = []
            module = SimpleNamespace(
                Image=_ImageAPI((100, 100)),
                compressed_image_bytes=lambda path: calls.append(Path(path).name) or b"jpeg",
            )
            photos = [SimpleNamespace(path=first), SimpleNamespace(path=second)]
            with patch.dict(
                os.environ,
                {
                    "PRODUCT_SORTER_PREPROCESS_WORKERS": "2",
                    "PRODUCT_SORTER_PREPROCESS_MEMORY_MB": "512",
                    "PRODUCT_SORTER_IMAGE_CACHE_ENTRIES": "24",
                },
                clear=False,
            ):
                preprocessor = performance_pipeline.BatchPreprocessor(module)
                preprocessor.warm(photos)
                preprocessor.warm(photos)

            self.assertCountEqual(["a.jpg", "b.jpg"], calls)
            self.assertEqual(1, preprocessor.stats["batches"])
            self.assertEqual(2, preprocessor.stats["images"])
            self.assertEqual(1, preprocessor.stats["skipped_cached_batches"])
            self.assertGreaterEqual(preprocessor.stats["max_workers_used"], 1)

    def test_preprocessor_skips_when_batch_cannot_fit_encoded_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name in ("a.jpg", "b.jpg"):
                path = root / name
                path.write_bytes(name.encode())
                paths.append(path)
            calls = []
            module = SimpleNamespace(
                Image=_ImageAPI((100, 100)),
                compressed_image_bytes=lambda path: calls.append(path) or b"jpeg",
            )
            photos = [SimpleNamespace(path=path) for path in paths]
            with patch.dict(
                os.environ,
                {
                    "PRODUCT_SORTER_PREPROCESS_WORKERS": "2",
                    "PRODUCT_SORTER_PREPROCESS_MEMORY_MB": "512",
                    "PRODUCT_SORTER_IMAGE_CACHE_ENTRIES": "1",
                },
                clear=False,
            ):
                preprocessor = performance_pipeline.BatchPreprocessor(module)
                preprocessor.warm(photos)
            self.assertEqual([], calls)
            self.assertEqual(1, preprocessor.stats["skipped_cache_capacity"])

    def test_stats_snapshot_reports_measured_throughput(self):
        with patch.dict(
            os.environ,
            {
                "PRODUCT_SORTER_PREPROCESS_WORKERS": "2",
                "PRODUCT_SORTER_PREPROCESS_MEMORY_MB": "512",
                "PRODUCT_SORTER_IMAGE_CACHE_ENTRIES": "24",
            },
            clear=False,
        ):
            snapshot = performance_pipeline._stats_snapshot(
                {"images": 10, "seconds": 2.0, "max_workers_used": 2}
            )
        self.assertEqual(5.0, snapshot["images_per_second"])
        self.assertEqual(2, snapshot["resolved_workers"])
        self.assertEqual(512, snapshot["memory_budget_mb"])

    def test_environment_validation_normalizes_worker_settings(self):
        environment_module = SimpleNamespace(
            _ENV_FIELDS=("AI_PROVIDERS",),
            _validate_setting=lambda name, value: value.strip(),
        )
        prepare_performance_environment_fields(environment_module)
        self.assertIn("PRODUCT_SORTER_PREPROCESS_WORKERS", environment_module._ENV_FIELDS)
        self.assertEqual(
            "auto",
            environment_module._validate_setting(
                "PRODUCT_SORTER_PREPROCESS_WORKERS", "auto"
            ),
        )
        self.assertEqual(
            "off",
            environment_module._validate_setting(
                "PRODUCT_SORTER_PREPROCESS_WORKERS", "disabled"
            ),
        )
        with self.assertRaises(ValueError):
            environment_module._validate_setting(
                "PRODUCT_SORTER_PREPROCESS_MEMORY_MB", "64"
            )


if __name__ == "__main__":
    unittest.main()
