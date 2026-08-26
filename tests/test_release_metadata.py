import re
import unittest
from pathlib import Path

from professional import VERSION


ROOT = Path(__file__).resolve().parent.parent


class ReleaseMetadataTests(unittest.TestCase):
    def test_pyproject_version_matches_application_version(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        self.assertIsNotNone(match)
        package_version = match.group(1)
        self.assertEqual(package_version, VERSION.replace("-rc", "rc"))

    def test_debian_package_derives_version_from_pyproject(self):
        script = (ROOT / "packaging" / "linux" / "build_deb.sh").read_text(encoding="utf-8")
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

    def test_release_builds_both_macos_architectures(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("macos-15-intel", workflow)
        self.assertIn("macos-arm64", workflow)
        self.assertIn("macos-x64", workflow)
        self.assertIn("ProductSorterPro-${{ matrix.artifact }}.zip", workflow)

    def test_macos_bundle_version_comes_from_pyproject(self):
        spec = (ROOT / "packaging" / "pyinstaller" / "product_sorter.spec").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("pyproject.toml", spec)
        self.assertIn('"CFBundleShortVersionString": APP_VERSION', spec)
        self.assertIn('"CFBundleVersion": APP_VERSION', spec)
        self.assertIn("Verify macOS bundle version", workflow)
        self.assertIn("CFBundleShortVersionString", workflow)
        self.assertIn("CFBundleVersion", workflow)


if __name__ == "__main__":
    unittest.main()
