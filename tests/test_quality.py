"""Datenqualitaetspruefung."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from trading_tool.quality import Severity, check_series

from .conftest import trending_session_series

HEUTE = date(2026, 9, 15)


@pytest.fixture
def reihe() -> pd.DataFrame:
    return trending_session_series(n=400, ende="2026-09-14")


def _bad_tick(frame: pd.DataFrame, position: int, faktor: float) -> pd.DataFrame:
    """Fehlerhaften Einzelkurs einbauen - Balken als Ganzes verschoben.

    Ein Datenfehler betrifft in der Regel den ganzen Balken, nicht nur den
    Schlusskurs. Nur so entsteht die Signatur, auf die geprueft wird:
    Sprung an einem Tag, Ruecknahme am naechsten.
    """
    frame = frame.copy()
    zeit = frame.index[position]
    for spalte in ("open", "high", "low", "close", "adj_close"):
        frame.loc[zeit, spalte] = frame.loc[zeit, spalte] * faktor
    return frame


def test_saubere_reihe_ohne_befund(reihe):
    bericht = check_series(reihe, "DE0007164600", HEUTE)
    assert bericht.ok, bericht.summary()
    assert bericht.severity is Severity.OK
    assert bericht.bars == 400


def test_leere_reihe_ist_eine_warnung():
    bericht = check_series(pd.DataFrame(), "DE0007164600", HEUTE)
    assert "leer" in bericht.codes
    assert bericht.severity is Severity.WARNUNG


def test_veraltete_reihe_wird_erkannt(reihe):
    """Indikatoren rechnen auf alten Daten stillschweigend weiter."""
    bericht = check_series(reihe.iloc[:-30], "X", HEUTE)
    assert "veraltet" in bericht.codes
    assert bericht.severity is Severity.WARNUNG


def test_wenige_tage_rueckstand_sind_kein_befund(reihe):
    """Ein Feiertag oder ein Wochenende darf keinen Alarm ausloesen."""
    assert "veraltet" not in check_series(reihe, "X", date(2026, 9, 18)).codes


def test_fehlerhafter_einzelkurs_wird_erkannt(reihe):
    """Die Signatur: Sprung an einem Tag, Ruecknahme am naechsten."""
    bericht = check_series(_bad_tick(reihe, -10, 1.45), "X", HEUTE)
    assert "ausreisser" in bericht.codes
    assert bericht.severity is Severity.WARNUNG


def test_echter_kurssprung_ohne_ruecknahme_ist_kein_befund(reihe):
    """Eine Uebernahmeprämie bleibt im Kurs - das ist keine Datenstoerung."""
    frame = reihe.copy()
    ab = frame.index[-40]
    for spalte in ("open", "high", "low", "close", "adj_close"):
        frame.loc[ab:, spalte] = frame.loc[ab:, spalte] * 1.4
    assert "ausreisser" not in check_series(frame, "X", HEUTE).codes


def test_alter_ausreisser_wiegt_leichter_als_ein_frischer(reihe):
    """Nur ein frischer Ausreisser kann das aktuelle Signal ausgeloest haben."""
    frisch = check_series(_bad_tick(reihe, -5, 1.45), "X", HEUTE)
    alt = check_series(_bad_tick(reihe, 100, 1.45), "X", HEUTE)
    assert frisch.severity is Severity.WARNUNG
    assert alt.severity is Severity.HINWEIS


def test_widerspruechlicher_balken_wird_erkannt(reihe):
    frame = reihe.copy()
    frame.loc[frame.index[-5], "high"] = frame.loc[frame.index[-5], "low"] * 0.5
    bericht = check_series(frame, "X", HEUTE)
    assert "ohlc" in bericht.codes
    assert bericht.severity is Severity.WARNUNG


def test_eingefrorene_reihe_wird_erkannt(reihe):
    """Eine Quelle, die denselben Kurs wiederholt, sieht ruhig aus statt kaputt."""
    frame = reihe.copy()
    letzte = frame.index[-15:]
    wert = float(frame.loc[letzte[0], "close"])
    for spalte in ("open", "high", "low", "close", "adj_close"):
        frame.loc[letzte, spalte] = wert
    assert "flatline" in check_series(frame, "X", HEUTE).codes


def test_fehlendes_volumen_wird_gemeldet(reihe):
    frame = reihe.copy()
    frame.loc[frame.index[-40:], "volume"] = 0.0
    bericht = check_series(frame, "X", HEUTE)
    assert "volumen" in bericht.codes
    # Fehlendes Volumen macht Regeln unzuverlaessig, aber die Reihe nicht falsch.
    assert bericht.severity is Severity.HINWEIS


def test_grosse_luecke_wird_gemeldet(reihe):
    """Jeden dritten Tag entfernen - das erklaert kein Feiertagskalender."""
    bericht = check_series(reihe.iloc[::3], "X", date(2026, 9, 16))
    assert "luecken" in bericht.codes


def test_schweregrad_ist_das_maximum_der_befunde(reihe):
    frame = _bad_tick(reihe, -8, 1.45)
    frame.loc[frame.index[-40:], "volume"] = 0.0
    bericht = check_series(frame, "X", HEUTE)
    assert {"ausreisser", "volumen"} <= set(bericht.codes)
    assert bericht.severity is Severity.WARNUNG


def test_bericht_nennt_die_befunde_im_klartext(reihe):
    bericht = check_series(reihe.iloc[:-30], "X", HEUTE)
    assert "Handelstagen" in bericht.summary()
    assert all(f.message and f.detail for f in bericht.findings)
