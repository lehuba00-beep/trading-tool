"""Paketierung: Sind alle Abhaengigkeiten deklariert, liegen alle Dateien bei?

Anlass fuer diese Tests: Der erste Windows-Build ist daran gescheitert, dass
eine im Entwicklungsrechner von Hand nachinstallierte Abhaengigkeit nicht in
``pyproject.toml`` stand. Lokal lief alles, im frischen CI-Container nichts.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIRST_PARTY = {"trading_tool", "conftest", "seed"}


def _declared_distributions() -> set[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    specs = set(project["dependencies"])
    for extra in project.get("optional-dependencies", {}).values():
        specs |= set(extra)

    names = set()
    for spec in specs:
        for separator in ("[", ">", "<", "=", "!", ";", " "):
            spec = spec.split(separator)[0]
        names.add(spec.strip().lower().replace("_", "-"))
    return names


def _imported_modules() -> dict[str, str]:
    """Fremdmodule mit der Datei, in der sie zuerst auftauchen."""
    modules: dict[str, str] = {}
    for path in sorted(ROOT.glob("src/**/*.py")) + sorted(ROOT.glob("tests/**/*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                found = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in found:
                if name and name not in sys.stdlib_module_names and name not in FIRST_PARTY:
                    modules.setdefault(name, str(path.relative_to(ROOT)))
    return modules


def test_alle_fremdimporte_sind_deklariert():
    declared = _declared_distributions()
    distributions = packages_distributions()

    fehlend = []
    for module, path in _imported_modules().items():
        dists = {d.lower().replace("_", "-") for d in distributions.get(module, [])}
        if not dists & declared:
            fehlend.append(f"{module} (in {path}, Distribution: {sorted(dists) or 'unbekannt'})")

    assert not fehlend, (
        "Diese Module werden importiert, stehen aber nicht in pyproject.toml. "
        "Lokal faellt das nicht auf, im frischen Container schon:\n  "
        + "\n  ".join(fehlend)
    )


def test_testclient_ist_benutzbar():
    """Starlette laedt seinen HTTP-Client erst zur Laufzeit nach - ein fehlender
    Eintrag faellt daher nicht durch die Import-Analyse, sondern nur hier."""
    from fastapi.testclient import TestClient  # noqa: F401


@pytest.mark.parametrize(
    "relativer_pfad",
    [
        "config/strategies/kurz_pullback.yaml",
        "config/strategies/kurz_ausbruch.yaml",
        "config/strategies/swing.yaml",
        "config/strategies/mittelfristig.yaml",
        "config/strategies/langfristig.yaml",
        "config/issuers.yaml",
        "universe/tr_universe.csv",
        "src/trading_tool/ui/static/app.css",
        "src/trading_tool/ui/static/poll.js",
        "src/trading_tool/ui/static/pwa.js",
        "src/trading_tool/ui/static/sw.js",
        "src/trading_tool/ui/static/manifest.webmanifest",
        "src/trading_tool/ui/static/icons/icon-192.png",
        "src/trading_tool/ui/static/icons/icon-512.png",
        "src/trading_tool/ui/static/icons/icon-maskable-512.png",
        "src/trading_tool/ui/templates/login.html",
        "src/trading_tool/ui/templates/base.html",
        "build/trading_tool.spec",
        "build/entry.py",
    ],
)
def test_mitgelieferte_datei_existiert(relativer_pfad):
    """Diese Dateien werden in die Exe gepackt - fehlt eine, startet sie nicht."""
    assert (ROOT / relativer_pfad).exists(), relativer_pfad


def test_startskript_laeuft_als_eigenstaendiges_skript():
    """Stellt die Startbedingung von PyInstaller nach.

    PyInstaller fuehrt sein Einstiegsskript als ``__main__`` aus, nicht als
    Modul eines Pakets - relative Importe scheitern dort. Genau daran ist die
    erste gebaute Exe gestorben, obwohl der Build selbst fehlerfrei durchlief.
    Dieser Test faengt das ohne Windows und ohne PyInstaller ab.
    """
    ergebnis = subprocess.run(
        [sys.executable, str(ROOT / "build" / "entry.py"), "rules"],
        capture_output=True, text=True, timeout=120,
        cwd=ROOT, env={**os.environ, "TRADING_TOOL_DATA_DIR": tempfile.mkdtemp()},
    )
    assert ergebnis.returncode == 0, ergebnis.stderr[-2000:]
    assert "Regelbausteine" in ergebnis.stdout


def test_paketmodul_direkt_aufgerufen_scheitert_wie_erwartet():
    """Die Gegenprobe: Warum es das Startskript ueberhaupt braucht."""
    ergebnis = subprocess.run(
        [sys.executable, str(ROOT / "src" / "trading_tool" / "__main__.py"), "rules"],
        capture_output=True, text=True, timeout=120, cwd=ROOT,
    )
    assert ergebnis.returncode != 0
    assert "relative import" in ergebnis.stderr


def test_spec_zeigt_auf_das_startskript():
    spec = (ROOT / "build" / "trading_tool.spec").read_text(encoding="utf-8")
    assert "entry.py" in spec
    assert 'SRC / "__main__.py"' not in spec, (
        "Das Einstiegsskript darf nicht direkt auf das Paketmodul zeigen"
    )


def test_spec_packt_alle_laufzeitdateien_ein():
    spec = (ROOT / "build" / "trading_tool.spec").read_text(encoding="utf-8")
    for pflicht in ['"config"', '"universe"', "ui\" / \"templates", "ui\" / \"static"]:
        assert pflicht in spec, f"{pflicht} fehlt in der PyInstaller-Spezifikation"
    # Ohne tzdata scheitert zoneinfo("Europe/Berlin") unter Windows.
    assert "tzdata" in spec
    # Der Rust-Anteil von cryptography wird dynamisch geladen und fehlt ohne
    # ausdrueckliche Nennung im Bundle - das faellt erst zur Laufzeit auf.
    assert "cryptography.hazmat.bindings._rust" in spec


def test_alle_templates_werden_verwendet():
    """Eine verwaiste Vorlage ist tote Fracht in der Exe."""
    templates = {p.name for p in (ROOT / "src/trading_tool/ui/templates").glob("*.html")}
    quellen = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list((ROOT / "src/trading_tool/ui").glob("*.py"))
        + list((ROOT / "src/trading_tool/ui/templates").glob("*.html"))
    )
    unbenutzt = {name for name in templates if name not in quellen}
    assert not unbenutzt, f"nicht referenzierte Vorlagen: {sorted(unbenutzt)}"
