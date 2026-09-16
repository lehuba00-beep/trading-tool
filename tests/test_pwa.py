"""Startbildschirm-App: Manifest, Service Worker, Icons, mobile Auszeichnung."""

from __future__ import annotations

import json

import pytest


def test_manifest_wird_ausgeliefert(client):
    antwort = client.get("/manifest.webmanifest")
    assert antwort.status_code == 200
    assert "manifest" in antwort.headers["content-type"]


def test_manifest_enthaelt_was_android_braucht(client):
    daten = json.loads(client.get("/manifest.webmanifest").text)
    assert daten["display"] == "standalone", "sonst bleibt die Browserleiste stehen"
    assert daten["start_url"] == "/"
    assert daten["scope"] == "/"
    assert daten["lang"] == "de"
    groessen = {i["sizes"] for i in daten["icons"]}
    assert {"192x192", "512x512"} <= groessen


def test_manifest_hat_ein_maskierbares_icon(client):
    """Ohne 'maskable' schneidet Android das Icon je nach Geraet beliebig zu."""
    daten = json.loads(client.get("/manifest.webmanifest").text)
    assert any(i.get("purpose") == "maskable" for i in daten["icons"])


def test_service_worker_liegt_an_der_wurzel(client):
    """Ein Service Worker steuert nur den Pfad, unter dem er selbst liegt."""
    antwort = client.get("/sw.js")
    assert antwort.status_code == 200
    assert antwort.headers.get("service-worker-allowed") == "/"
    assert "javascript" in antwort.headers["content-type"]


def test_service_worker_speichert_kurse_niemals_zwischen(client):
    """Ein zwischengespeicherter Kurs waere schlimmer als gar keiner - er
    sieht aktuell aus und ist es nicht."""
    quelltext = client.get("/sw.js").text
    for pfad in ["/kurse", "/jobs/status", "/anmelden"]:
        assert pfad in quelltext
    assert "NIEMALS_ZWISCHENSPEICHERN" in quelltext


@pytest.mark.parametrize("name", ["icon-192.png", "icon-512.png", "icon-maskable-512.png",
                                  "favicon.png"])
def test_icons_werden_ausgeliefert(client, name):
    antwort = client.get(f"/icons/{name}")
    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "image/png"
    assert antwort.content[:8] == b"\x89PNG\r\n\x1a\n", "keine gueltige PNG-Datei"


def test_icon_pfad_laesst_sich_nicht_verlassen(client):
    """Ohne Einsperrung liesse sich ueber ../ jede Datei des Rechners abrufen."""
    antwort = client.get("/icons/..%2f..%2f..%2fetc%2fpasswd", follow_redirects=False)
    assert antwort.status_code in (303, 404)
    assert b"root:" not in antwort.content


def test_seite_verweist_auf_manifest_und_icons(client):
    text = client.get("/").text
    assert 'rel="manifest"' in text
    assert 'name="theme-color"' in text
    assert "apple-touch-icon" in text
    assert "/static/pwa.js" in text


def test_registrierung_scheitert_leise(client):
    """Browser ohne Unterstuetzung duerfen keine Fehlermeldung sehen."""
    quelltext = client.get("/static/pwa.js").text
    assert "serviceWorker" in quelltext
    assert "catch" in quelltext


# ------------------------------------------------------ Mobile Auszeichnung

def test_trefferliste_ist_fuer_die_kartenansicht_ausgezeichnet(
    client, seeded, settings, strategies
):
    """Auf dem Handy wird jede Zeile zu einer Karte. Die Beschriftungen kommen
    aus data-label - ohne sie stuenden dort nackte Zahlen ohne Bedeutung."""
    from trading_tool.providers.registry import ProviderChain
    from trading_tool.screener.engine import Screener
    from trading_tool.storage.cache import PriceCache

    Screener(seeded, PriceCache(seeded, ProviderChain(settings), settings),
             settings, strategies).run("swing", refresh=False)

    text = client.get("/screener/swing").text
    for beschriftung in ['data-label="Kurs (EUR)"', 'data-label="20 Tage"',
                         'data-label="Stop (aus dem Lauf)"', 'data-label="Umsatz"',
                         'data-label="Trade Republic"']:
        assert beschriftung in text, beschriftung
    assert 'class="cell-title"' in text


@pytest.mark.parametrize("pfad", ["/universe", "/datenqualitaet"])
def test_weitere_tabellen_sind_ausgezeichnet(client, pfad):
    assert "data-label=" in client.get(pfad).text


def test_watchlist_ist_ausgezeichnet(client):
    """Die leere Watchlist hat keine Zeilen - erst mit Eintrag pruefbar."""
    client.post("/watchlist/add", data={"isin": "DE0007164600"})
    assert "data-label=" in client.get("/watchlist").text


def test_stylesheet_bringt_die_kartenansicht_mit(client):
    css = client.get("/static/app.css").text
    assert "max-width: 720px" in css
    assert "attr(data-label)" in css
    assert "cell-title" in css
