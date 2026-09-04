import importlib
import subprocess
import sys
import textwrap
import unittest

MODULES = [
    "review_center_gui", "sku_matching_gui", "catalog_exports_gui", "benchmark_gui",
    "environment_gui", "report_gui", "rclone_gui", "automation_gui",
]

class TranslationCatalogParityTests(unittest.TestCase):
    def test_known_gui_catalogs_have_equal_language_keys(self):
        for leaf in MODULES:
            module = importlib.import_module(f"ai_product_photo_sorter.{leaf}")
            catalog = getattr(module, "_TEXT", None)
            if catalog is None:
                continue
            with self.subTest(module=leaf):
                self.assertEqual(set(catalog), {"en","ar","zh"})
                self.assertEqual(set(catalog["en"]), set(catalog["ar"]))
                self.assertEqual(set(catalog["en"]), set(catalog["zh"]))

    def test_review_catalog_import_does_not_require_imagetk(self):
        code = textwrap.dedent(
            """
            import builtins
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path.cwd() / "src"))
            real_import = builtins.__import__

            def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == "PIL" and "ImageTk" in (fromlist or ()):
                    raise ImportError("simulated missing PIL.ImageTk")
                return real_import(name, globals, locals, fromlist, level)

            builtins.__import__ = guarded_import
            import ai_product_photo_sorter.review_center_gui as module
            assert set(module._TEXT) == {"en", "ar", "zh"}
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

if __name__ == "__main__":
    unittest.main()
