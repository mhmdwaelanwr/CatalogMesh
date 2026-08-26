# Build with: pyinstaller --clean product_sorter.spec
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


def project_version():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to read project version from pyproject.toml")
    return match.group(1)


APP_VERSION = project_version()
datas=[]; hidden=[]
for package in ("google.genai","PIL","openpyxl","keyring"):
    d,b,h=collect_all(package); datas+=d; hidden+=h
a=Analysis(["product_sorter_gui.py"],pathex=[],binaries=[],datas=datas+[(".env.example","."),("requirements.txt","."),("provider_models.json","."),("assets/branding","assets/branding")],hiddenimports=hidden)
pyz=PYZ(a.pure)
app_icon="assets/branding/product-sorter.icns" if sys.platform=="darwin" else "assets/branding/product-sorter.ico"
exe=EXE(pyz,a.scripts,a.binaries,a.datas,name="ProductSorterPro",console=False,icon=app_icon)
if sys.platform=="darwin":
    app=BUNDLE(
        exe,
        name="ProductSorterPro.app",
        icon="assets/branding/product-sorter.icns",
        bundle_identifier="io.github.mhmdwaelanwr.product-sorter",
        info_plist={
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
        },
    )
