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


def test_hintergrundlauf_wird_beim_beenden_gestoppt(seeded, settings):
    """Ohne geordnetes Beenden bleibt je Anwendungsinstanz ein Thread stehen -
    und der Abbau haengt an einem noch laufenden Auftrag."""
    import threading

    vorher = threading.active_count()
    app = create_app(settings)
    with TestClient(app) as client:
        client.post("/screener/swing/run")
    assert not app.state.app.jobs._worker.is_alive()
    assert threading.active_count() <= vorher, "Arbeitsthread ueberlebt das Beenden"


def test_eingereihter_auftrag_nach_dem_stopp_wird_abgelehnt(settings):
    from trading_tool.ui.jobs import JobRunner

    runner = JobRunner()
    runner.stop()
    assert runner.submit("x", "X", lambda progress: {}) is False


# ----------------------------------------------------- Laufende Kurse (UI)

def test_kurs_endpunkt_antwortet_ohne_isins(client):
    antwort = client.get("/kurse")
    assert antwort.status_code == 200
    assert antwort.json()["kurse"] == {}


def test_kurs_endpunkt_ohne_kursquelle_liefert_leer(client):
    """Im Test gibt es keinen Anbieter fuer laufende Kurse - die Seite muss
    trotzdem antworten und die Schlusskurse stehen lassen."""
    antwort = client.get("/kurse", params={"isins": "DE0007164600,US0378331005"})
    assert antwort.status_code == 200
    assert antwort.json()["kurse"] == {}


def test_kurs_endpunkt_liefert_preis_und_veraenderung(client, seeded, settings):
    from datetime import datetime

    from trading_tool.providers.quotes import Quote

    class FesterDienst:
        def get(self, instrumente):
            return {
                i.isin: Quote(symbol=i.ticker_yahoo, price=123.456, previous_close=120.0,
                              fetched_at=datetime(2026, 9, 16, 14, 30))
                for i in instrumente
            }

        def status(self):
            return {"aktiv": True, "abgerufen": "14:30:00", "symbole": 1,
                    "fehler": "", "intervall": 30}

    client.app.state.app.quotes = FesterDienst()
    daten = client.get("/kurse", params={"isins": "DE0007164600"}).json()
    assert daten["kurse"]["DE0007164600"]["preis"] == pytest.approx(123.456)
    assert daten["kurse"]["DE0007164600"]["veraenderung"] == pytest.approx(2.88, abs=0.01)
    assert daten["abgerufen"] == "14:30:00"


def test_unbekannte_isin_wird_ausgelassen(client):
    antwort = client.get("/kurse", params={"isins": "DE9999999999"})
    assert antwort.status_code == 200
    assert antwort.json()["kurse"] == {}


def test_trefferliste_markiert_die_kurszellen(client, seeded, settings, strategies):
    """Ohne die Markierung findet das Skript die Zellen nicht."""
    from trading_tool.providers.registry import ProviderChain
    from trading_tool.screener.engine import Screener
    from trading_tool.storage.cache import PriceCache

    Screener(seeded, PriceCache(seeded, ProviderChain(settings), settings),
             settings, strategies).run("swing", refresh=False)

    text = client.get("/screener/swing").text
    assert 'data-kurs="' in text
    assert "kurs-wert" in text


def test_seite_traegt_das_abfrageintervall(client):
    assert 'data-kurs-intervall="30"' in client.get("/").text


def test_abgeschaltete_kurse_setzen_das_intervall_auf_null(seeded, settings):
    settings.schedule.enabled = False
    settings.quotes.enabled = False
    app = create_app(settings)
    with TestClient(app) as c:
        assert 'data-kurs-intervall="0"' in c.get("/").text


# --------------------------------------------------------- Datenqualitaet

def test_datenqualitaet_ist_erreichbar(client):
    antwort = client.get("/datenqualitaet")
    assert antwort.status_code == 200
    assert "Datenqualität" in antwort.text


def test_datenqualitaet_erklaert_die_pruefungen(client):
    text = client.get("/datenqualitaet").text
    for begriff in ["Veraltet", "Kurssprünge", "Widersprüchliche", "Eingefrorene"]:
        assert begriff in text


def test_datenqualitaet_meldet_titel_ohne_kursdaten(client, seeded):
    """Die meisten Titel aus der mitgelieferten Liste haben im Test keine
    Kursreihe - genau das soll die Seite zeigen."""
    text = client.get("/datenqualitaet").text
    assert "keine Kursdaten" in text


def test_datenqualitaet_kann_alle_titel_zeigen(client):
    assert client.get("/datenqualitaet", params={"nur_probleme": 0}).status_code == 200


def test_navigation_verlinkt_die_datenqualitaet(client):
    assert 'href="/datenqualitaet"' in client.get("/").text


# ------------------------------------------------- Stop und Ziel im Chart

def test_chart_zeigt_stop_und_ziel_bei_gewaehlter_strategie(client):
    text = client.get("/instrument/DE0007164600", params={"strategie": "swing"}).text
    assert 'class="level stop"' in text
    assert 'class="level ziel"' in text
    assert 'class="level einstieg"' in text
    assert "Stop " in text and "Ziel " in text


def test_chart_ohne_strategie_zeigt_keine_marken(client):
    """Ohne Strategie gibt es keinen ATR-Stop - dann auch keine Linie."""
    text = client.get("/instrument/DE0007164600").text
    assert 'class="level stop"' not in text


def test_marken_passen_zur_risikovorgabe_der_strategie(client, strategies):
    text = client.get("/instrument/DE0007164600", params={"strategie": "swing"}).text
    faktor = strategies["swing"].risk.stop_atr_factor
    assert f"{faktor:.1f}".replace(".", ",") in text


def test_laufender_kurs_ist_als_solcher_beschriftet(client, seeded, settings, strategies):
    """Stop und Ziel stammen aus dem Lauf, der Kurs daneben ist laufend -
    ohne Beschriftung liest man zwei Zahlen aus verschiedenen Zeitpunkten
    nebeneinander wie eine."""
    from trading_tool.providers.registry import ProviderChain
    from trading_tool.screener.engine import Screener
    from trading_tool.storage.cache import PriceCache

    Screener(seeded, PriceCache(seeded, ProviderChain(settings), settings),
             settings, strategies).run("swing", refresh=False)

    text = client.get("/screener/swing").text
    assert "laufend" in text
    assert "nicht laufend angepasst" in text


def test_instrumentenseite_trennt_laufenden_kurs_von_kennzahlen(client):
    text = client.get("/instrument/DE0007164600", params={"strategie": "swing"}).text
    assert "Nur der Kurs wird laufend aktualisiert" in text
