"""Oberflaeche: Routen, Darstellung und die Bedienschritte, die Zustand aendern.

Die Tests laufen gegen die echte Anwendung mit synthetischen Kursdaten - ohne
Netz, ohne Zeitsteuerung.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trading_tool.domain.enums import TRStatus
from trading_tool.storage.repositories import InstrumentRepo, WatchlistRepo
from trading_tool.ui.app import _money, _number, create_app
from trading_tool.ui.charts import candlestick

from .conftest import trending_series


@pytest.fixture
def client(seeded, settings):
    settings.schedule.enabled = False  # keine Hintergrundlaeufe im Test
    settings.ui.open_browser = False
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def test_startseite_zeigt_alle_strategien(client):
    response = client.get("/")
    assert response.status_code == 200
    for label in ["Ruecksetzer", "Ausbruch", "Swing", "Mittelfristig", "Langfristig"]:
        assert label in response.text


def test_startseite_traegt_den_beratungshinweis(client):
    """Der Hinweis gehoert auf jede Seite, nicht in ein Untermenue."""
    assert "Keine Anlageberatung" in client.get("/").text


def test_jede_hauptseite_antwortet(client):
    for pfad in ["/", "/watchlist", "/universe", "/einstellungen",
                 "/screener/swing", "/trefferquote/swing"]:
        assert client.get(pfad).status_code == 200, pfad


def test_unbekannte_strategie_leitet_zur_startseite(client):
    response = client.get("/screener/gibt_es_nicht", follow_redirects=False)
    assert response.status_code == 303


def test_universum_wird_beim_start_geladen(client):
    response = client.get("/universe")
    assert response.status_code == 200
    assert "SAP" in response.text


def test_universum_laesst_sich_durchsuchen(client):
    response = client.get("/universe", params={"q": "Apple"})
    assert "Apple" in response.text
    assert "Siemens" not in response.text


def test_universum_laesst_sich_nach_status_filtern(client):
    assert client.get("/universe", params={"status": "verified"}).status_code == 200


def test_tr_status_laesst_sich_aus_der_oberflaeche_setzen(client, seeded):
    """Der Kern des Pflege-Workflows: Die Liste verbessert sich dort, wo sie
    benutzt wird."""
    response = client.post("/universe/DE0007164600/status", data={"status": "verified"},
                           follow_redirects=False)
    assert response.status_code == 303
    instrument = InstrumentRepo(seeded).get("DE0007164600")
    assert instrument.tr_status is TRStatus.VERIFIED
    assert instrument.tr_checked_at is not None


def test_nicht_handelbar_laesst_sich_markieren(client, seeded):
    client.post("/universe/DE0007164600/status", data={"status": "unavailable"})
    assert InstrumentRepo(seeded).get("DE0007164600").tr_status is TRStatus.UNAVAILABLE


def test_unbekannter_status_wird_ignoriert(client, seeded):
    client.post("/universe/DE0007164600/status", data={"status": "quatsch"})
    assert InstrumentRepo(seeded).get("DE0007164600").tr_status is TRStatus.ASSUMED


def test_watchlist_aufnehmen_und_entfernen(client, seeded):
    client.post("/watchlist/add", data={"isin": "DE0007164600"})
    assert "DE0007164600" in WatchlistRepo(seeded).isins()
    assert "SAP" in client.get("/watchlist").text

    client.post("/watchlist/remove", data={"isin": "DE0007164600"})
    assert WatchlistRepo(seeded).isins() == []


def test_nicht_handelbare_titel_kommen_nicht_auf_die_watchlist(client, seeded):
    """Damit bleibt die Anforderung 'nur bei TR handelbar' durchgehend erfuellt."""
    client.post("/watchlist/add", data={"isin": "IDX_MSCIWORLD"})
    assert WatchlistRepo(seeded).isins() == []


def test_unbekannte_isin_kommt_nicht_auf_die_watchlist(client, seeded):
    client.post("/watchlist/add", data={"isin": "DE9999999999"})
    assert WatchlistRepo(seeded).isins() == []


def test_instrumentenseite_zeigt_chart_und_kennzahlen(client):
    response = client.get("/instrument/DE0007164600")
    assert response.status_code == 200
    assert "<svg" in response.text
    assert "RSI(14)" in response.text


def test_instrumentenseite_zeigt_die_regelauswertung(client):
    """Eine nackte Zahl ist nicht ueberpruefbar - die Einzelregeln gehoeren dazu."""
    response = client.get("/instrument/DE0007164600", params={"strategie": "swing"})
    assert "Regelauswertung" in response.text
    assert "Pflicht" in response.text


def test_instrumentenseite_zeigt_hebelmathematik(client):
    response = client.get("/instrument/DE0007164600", params={"strategie": "kurz_ausbruch"})
    assert "Knock-Out" in response.text
    assert "Emittentenrisiko" in response.text


def test_langfristige_signale_ohne_hebelprodukte(client):
    response = client.get("/instrument/DE0007164600", params={"strategie": "langfristig"})
    assert "nicht das passende Vehikel" in response.text


def test_fremdwaehrung_wird_als_umgerechnet_ausgewiesen(client):
    response = client.get("/instrument/US0378331005")
    assert "nach EUR umgerechnet" in response.text


def test_unbekanntes_instrument_leitet_zum_universum(client):
    response = client.get("/instrument/DE9999999999", follow_redirects=False)
    assert response.status_code == 303


def test_screening_laesst_sich_ausloesen_und_der_status_abfragen(client):
    assert client.post("/screener/swing/run", follow_redirects=False).status_code == 303
    assert client.get("/jobs/status").status_code == 200


def test_export_ohne_lauf_leitet_zurueck(client):
    response = client.get("/export/swing.csv", follow_redirects=False)
    assert response.status_code == 303


def test_export_liefert_eine_datei(client, seeded, settings, strategies):
    from trading_tool.providers.registry import ProviderChain
    from trading_tool.screener.engine import Screener
    from trading_tool.storage.cache import PriceCache

    screener = Screener(seeded, PriceCache(seeded, ProviderChain(settings), settings),
                        settings, strategies)
    screener.run("swing", refresh=False)

    response = client.get("/export/swing.csv")
    assert response.status_code == 200
    assert "isin;name;strategie" in response.text.lower()


# --------------------------------------------------------------- Darstellung

def test_zahlen_erscheinen_in_deutscher_schreibweise():
    assert _number(1234567.891) == "1.234.567,89"
    assert _number(0.5, 1) == "0,5"
    assert _number(None) == "-"
    assert _number("keine Zahl") == "keine Zahl"


def test_geldbetraege_werden_gekuerzt():
    assert _money(2_500_000) == "2,5 Mio."
    assert _money(12_000) == "12 Tsd."
    assert _money(None) == "-"


def test_chart_liefert_svg_mit_kerzen_und_overlay():
    frame = trending_series(n=300)
    svg = candlestick(frame, {"SMA 50": frame["close"].rolling(50).mean()}, bars=120)
    assert svg.count("<rect") > 120  # Kerzen und Volumenbalken
    assert "polyline" in svg
    assert "SMA 50" in svg


def test_chart_kommt_mit_leerer_reihe_klar():
    import pandas as pd

    assert "Keine Kursdaten" in candlestick(pd.DataFrame())
