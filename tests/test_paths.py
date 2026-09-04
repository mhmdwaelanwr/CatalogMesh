import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_product_photo_sorter import paths, setup_wizard


class PathsTests(unittest.TestCase):
    def _frozen_patches(self, *, platform: str, executable: Path, bundle: Path, env: dict[str, str]):
        return (
            mock.patch.object(paths.sys, "frozen", True, create=True),
            mock.patch.object(paths.sys, "platform", platform),
            mock.patch.object(paths.sys, "executable", str(executable)),
            mock.patch.object(paths.sys, "_MEIPASS", str(bundle), create=True),
            mock.patch.dict(paths.os.environ, env, clear=True),
        )

    def test_runtime_root_still_uses_pyinstaller_bundle_for_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "app" / "CatalogMesh.exe"
            bundle = root / "_MEI12345"
            executable.parent.mkdir(parents=True)
            bundle.mkdir()
            patches = self._frozen_patches(
                platform="win32",
                executable=executable,
                bundle=bundle,
                env={"LOCALAPPDATA": str(root / "local")},
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                self.assertEqual(paths.runtime_root(), bundle.resolve())

    def test_frozen_windows_config_uses_local_appdata_not_meipass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "app" / "CatalogMesh.exe"
            bundle = root / "_MEI54321"
            local = root / "LocalAppData"
            executable.parent.mkdir(parents=True)
            bundle.mkdir()
            patches = self._frozen_patches(
                platform="win32",
                executable=executable,
                bundle=bundle,
                env={"LOCALAPPDATA": str(local)},
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                self.assertEqual(paths.env_file(), local.resolve() / "CatalogMesh" / ".env")
                self.assertNotEqual(paths.env_file().parent, bundle.resolve())

    def test_frozen_windows_existing_adjacent_env_enables_portable_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "portable" / "CatalogMesh.exe"
            bundle = root / "_MEI99999"
            executable.parent.mkdir(parents=True)
            bundle.mkdir()
            portable_env = executable.parent / ".env"
            portable_env.write_text("APP_THEME=dark\n", encoding="utf-8")
            patches = self._frozen_patches(
                platform="win32",
                executable=executable,
                bundle=bundle,
                env={"LOCALAPPDATA": str(root / "local")},
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                self.assertEqual(paths.env_file(), portable_env.resolve())

    def test_frozen_macos_config_uses_application_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "CatalogMesh.app" / "Contents" / "MacOS" / "CatalogMesh"
            bundle = root / "_MEImac"
            home = root / "home"
            executable.parent.mkdir(parents=True)
            bundle.mkdir()
            patches = self._frozen_patches(
                platform="darwin",
                executable=executable,
                bundle=bundle,
                env={},
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], mock.patch.object(paths.Path, "home", return_value=home):
                self.assertEqual(
                    paths.env_file(),
                    home / "Library" / "Application Support" / "CatalogMesh" / ".env",
                )

    def test_frozen_linux_config_honors_xdg_config_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "bin" / "catalogmesh"
            bundle = root / "_MEIlinux"
            xdg = root / "xdg"
            executable.parent.mkdir(parents=True)
            bundle.mkdir()
            patches = self._frozen_patches(
                platform="linux",
                executable=executable,
                bundle=bundle,
                env={"XDG_CONFIG_HOME": str(xdg)},
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                self.assertEqual(paths.env_file(), xdg.resolve() / "CatalogMesh" / ".env")

    def test_non_frozen_env_file_keeps_legacy_runtime_root_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(paths.sys, "frozen", False, create=True), mock.patch.object(
                paths, "runtime_root", return_value=root
            ):
                self.assertEqual(paths.env_file(), root / ".env")

    def test_setup_writer_creates_missing_config_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "CatalogMesh" / ".env"
            self.assertFalse(target.parent.exists())
            setup_wizard._save_env({"APP_THEME": "dark"}, target)
            self.assertTrue(target.is_file())
            self.assertIn("APP_THEME=dark", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
