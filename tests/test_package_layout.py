import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "ai_product_photo_sorter"


class PackageLayoutTests(unittest.TestCase):
    def test_internal_runtime_modules_live_under_src_package(self):
        for name in ("sorter_core.py", "providers.py", "professional.py", "i18n.py", "secrets_store.py", "model_catalog.py", "provider_models.json"):
            with self.subTest(name=name):
                self.assertFalse((ROOT / name).exists(), name)
        for name in ("core.py", "providers.py", "professional.py", "i18n.py", "secrets_store.py", "model_catalog.py", "provider_models.json", "benchmark.py", "benchmark_gui.py", "benchmark_reproducibility.py", "resource_lifecycle.py", "key_validation.py", "provider_selection.py", "provider_gui.py"):
            with self.subTest(name=name):
                self.assertTrue((PACKAGE / name).is_file(), name)

    def test_v31_core_import_path_points_to_same_engine(self):
        import sorter_core
        from ai_product_photo_sorter import _core_impl

        self.assertIs(sorter_core, _core_impl)

    def test_source_checkout_keeps_configuration_at_repository_root(self):
        import sorter_core
        import set_data

        self.assertEqual(sorter_core.DEFAULT_ENV_FILE, ROOT / ".env")
        self.assertEqual(set_data.ENV_FILE, ROOT / ".env")

    def test_console_entry_points_use_package_namespace(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(text, r'product-sorter\s*=\s*"ai_product_photo_sorter\.cli:main"')
        self.assertRegex(text, r'product-sorter-setup\s*=\s*"ai_product_photo_sorter\.setup_wizard:main"')
        self.assertRegex(text, r'product-sorter-gui\s*=\s*"ai_product_photo_sorter\.gui:main"')

    def test_package_catalog_is_bundled_next_to_model_catalog(self):
        from ai_product_photo_sorter import model_catalog

        self.assertEqual(model_catalog.CATALOG_FILE.parent, PACKAGE)
        self.assertTrue(model_catalog.CATALOG_FILE.is_file())


if __name__ == "__main__":
    unittest.main()
