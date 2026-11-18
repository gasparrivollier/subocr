# PyInstaller spec: folder-mode build named "subocr" (windowed). Build with:
#   pyinstaller packaging/subocr_app.spec --noconfirm
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.dirname(SPECPATH)

datas, binaries, hiddenimports = [], [], []
for pkg in ("rapidocr", "onnxruntime", "subocr"):  # OCR models + configs, ONNX runtime libs, our images
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(SPECPATH, "app_entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="subocr", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="subocr")
