import re
import unittest
from pathlib import Path

from professional import VERSION


ROOT = Path(__file__).resolve().parent.parent


class ReleaseMetadataTests(unittest.TestCase):
    def project_text(self) -> str:
        return (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    def project_version(self) -> str:
        text = self.project_text()
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_primary_pypi_project_is_catalogmesh(self):
        text = self.project_text()
        self.assertRegex(text, r'(?m)^name\s*=\s*"catalogmesh"$')
        self.assertIn('readme = "PYPI_README.md"', text)

    def test_pyproject_version_matches_application_version(self):
        self.assertEqual(self.project_version(), VERSION.replace("-rc", "rc"))

    def test_debian_package_derives_version_from_pyproject(self):
        script = (ROOT / "packaging" / "linux" / "build_deb.sh").read_text(encoding="utf-8")
        self.assertIn("pyproject.toml", script)
        self.assertNotRegex(script, r'(?m)^version=["\']\d+\.\d+\.\d+["\']')

    def test_readme_stable_release_matches_project_version(self):
        version = self.project_version()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"release-{version}-4f8cff", readme)
        self.assertIn(f"stable `v{version}` release", readme)
        self.assertIn(f"product-sorter-pro_{version}_all.deb", readme)

    def test_release_notes_exist_for_project_version(self):
        notes = ROOT / "docs" / "releases" / f"v{self.project_version()}.md"
        self.assertTrue(notes.is_file(), notes)

    def test_release_trigger_matches_project_version(self):
        trigger = (ROOT / ".github" / "release-trigger").read_text(encoding="utf-8").strip()
        self.assertEqual(trigger, f"v{self.project_version()}")

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

    def test_release_targets_catalogmesh_pypi(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("dist/catalogmesh-*", workflow)
        self.assertIn("https://pypi.org/project/catalogmesh/", workflow)

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
