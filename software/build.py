# build.py - crea dist\Super8Scan.exe con PyInstaller:  .venv\Scripts\python.exe build.py
import os, re, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
if not os.path.normcase(sys.prefix).startswith(os.path.normcase(os.path.join(ROOT, ".venv"))):
    sys.exit("Esegui la build con l'ambiente virtuale: .venv\Scripts\python.exe build.py")
VERSION = re.search(r'^VERSION = "([\d.]+)"', open("super8scan.py", encoding="utf-8").read(), re.M).group(1)
vt = tuple(int(n) for n in (VERSION.split(".") + ["0"] * 4)[:4])
os.makedirs("build", exist_ok=True)
with open(os.path.join("build", "version_info.txt"), "w", encoding="utf-8") as f:
    f.write(f"""VSVersionInfo(ffi=FixedFileInfo(filevers={vt}, prodvers={vt}), kids=[
 StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName', 'FallingBit'),
  StringStruct('FileDescription', 'Super8Scan - Super8 frame grabber'), StringStruct('FileVersion', '{VERSION}'),
  StringStruct('InternalName', 'Super8Scan'), StringStruct('OriginalFilename', 'Super8Scan.exe'),
  StringStruct('ProductName', 'Super8Scan'), StringStruct('ProductVersion', '{VERSION}')])]),
 VarFileInfo([VarStruct('Translation', [1033, 1200])])])""")
DIST = sys.argv[1] if len(sys.argv) > 1 else "dist"   # cartella di destinazione (se l'exe è in uso passa un altro nome)
import PyInstaller.__main__
PyInstaller.__main__.run([
    "super8scan.py", "--name", "Super8Scan", "--onefile", "--windowed", "--noconfirm", "--clean",
    "--icon", os.path.join(ROOT, "res", "icona.ico"),
    "--version-file", os.path.join(ROOT, "build", "version_info.txt"),
    "--add-data", os.path.join(ROOT, "ui") + os.pathsep + "ui",
    "--add-data", os.path.join(ROOT, "res", "icona.ico") + os.pathsep + "res",
    "--collect-all", "webview",
    *[a for m in ("PIL", "tkinter", "unittest", "pydoc") for a in ("--exclude-module", m)],
    "--distpath", DIST, "--workpath", os.path.join("build", "work"), "--specpath", "build"])
print("Fatto:", os.path.join(ROOT, DIST, "Super8Scan.exe"))
