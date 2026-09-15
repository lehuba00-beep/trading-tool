# PyInstaller-Spezifikation.
#
# Bewusst one-dir statt one-file: Eine one-file-Exe entpackt bei jedem Start
# pandas, numpy und die Templates nach %TEMP%. Das kostet bei diesem
# Abhaengigkeitsumfang mehrere Sekunden - jedes Mal.
#
# Bauen (auf einem Windows-Rechner oder im Windows-Runner):
#     pyinstaller build/trading_tool.spec --noconfirm

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src" / "trading_tool"

datas = [
    # Vorlagen und Stammdaten. Beim ersten Start werden sie ins beschreibbare
    # Nutzerverzeichnis kopiert, damit Aenderungen ein Update ueberleben.
    (str(ROOT / "config"), "config"),
    (str(ROOT / "universe" / "tr_universe.csv"), "universe"),
    (str(SRC / "ui" / "templates"), "trading_tool/ui/templates"),
    (str(SRC / "ui" / "static"), "trading_tool/ui/static"),
]

hiddenimports = [
    # uvicorn laedt seine Protokoll- und Schleifenimplementierungen zur
    # Laufzeit nach; PyInstaller sieht diese Importe nicht.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # Zeitzonendatenbank - Windows hat keine eigene.
    "tzdata",
    "zoneinfo",
] + collect_submodules("apscheduler") + collect_submodules("trading_tool")

a = Analysis(
    # Nicht direkt auf trading_tool/__main__.py zeigen: PyInstaller fuehrt das
    # Einstiegsskript als __main__ aus, wodurch dort jeder relative Import
    # scheitert. entry.py importiert das Paket stattdessen absolut.
    [str(ROOT / "build" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide6", "IPython", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="TradingTool",
    debug=False,
    strip=False,
    upx=False,
    # Konsole bleibt sichtbar: Sie zeigt die Adresse der Oberflaeche und im
    # Fehlerfall die Ursache. Ohne sie waere ein Fehlstart ein stummes Nichts.
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="TradingTool",
)
