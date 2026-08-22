# Build with: pyinstaller --clean product_sorter.spec
import sys
from PyInstaller.utils.hooks import collect_all
datas=[]; hidden=[]
for package in ("google.genai","PIL","openpyxl","keyring"):
    d,b,h=collect_all(package); datas+=d; hidden+=h
a=Analysis(["product_sorter_gui.py"],pathex=[],binaries=[],datas=datas+[(".env.example","."),("requirements.txt","."),("provider_models.json","."),("assets/branding","assets/branding")],hiddenimports=hidden)
pyz=PYZ(a.pure)
app_icon="assets/branding/product-sorter.icns" if sys.platform=="darwin" else "assets/branding/product-sorter.ico"
exe=EXE(pyz,a.scripts,a.binaries,a.datas,name="ProductSorterPro",console=False,icon=app_icon)
