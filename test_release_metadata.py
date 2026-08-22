import re
import unittest
from pathlib import Path

from professional import VERSION


ROOT = Path(__file__).resolve().parent


class ReleaseMetadataTests(unittest.TestCase):
    def test_pyproject_version_matches_application_version(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        self.assertIsNotNone(match)
        package_version = match.group(1)
        self.assertEqual(package_version, VERSION.replace("-rc", "rc"))

    def test_debian_package_derives_version_from_pyproject(self):
        script = (ROOT / "build_deb.sh").read_text(encoding="utf-8")
        self.assertIn("pyproject.toml", script)
        self.assertNotIn('version="3.1.0', script)

    def test_release_brand_assets_exist(self):
        branding = ROOT / "assets" / "branding"
        for name in (
            "product-sorter.ico",
            "product-sorter.icns",
            "product-sorter-256.png",
            "product-sorter-logo.svg",
        ):
            with self.subTest(name=name):
                self.assertTrue((branding / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
