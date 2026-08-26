# Build with: pyinstaller --clean packaging/pyinstaller/product_sorter.spec
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve().parents[1]


def repo_path(*parts: str) -> str:
    return str(ROOT.joinpath(*parts))


def project_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to read project version from pyproject.toml")
    return match.group(1)


APP_VERSION = project_version()
datas = []
hidden = []
for package in ("google.genai", "PIL", "openpyxl", "keyring"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    hidden += package_hidden

a = Analysis(
    [repo_path("product_sorter_gui.py")],
    pathex=[repo_path("src"), str(ROOT)],
    binaries=[],
    datas=datas + [
        (repo_path(".env.example"), "."),
        (repo_path("requirements.txt"), "."),
        (repo_path("src", "ai_product_photo_sorter", "provider_models.json"), "ai_product_photo_sorter"),
        (repo_path("assets", "branding"), "assets/branding"),
    ],
    hiddenimports=hidden,
)
pyz = PYZ(a.pure)
app_icon = repo_path(
    "assets", "branding", "product-sorter.icns" if sys.platform == "darwin" else "product-sorter.ico"
)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="ProductSorterPro",
    console=False,
    icon=app_icon,
)
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="ProductSorterPro.app",
        icon=repo_path("assets", "branding", "product-sorter.icns"),
        bundle_identifier="io.github.mhmdwaelanwr.product-sorter",
        info_plist={
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
        },
    )
