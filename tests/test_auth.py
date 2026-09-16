"""Passwortschutz fuer den Zugriff aus dem Netz."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from trading_tool.ui.app import create_app
from trading_tool.ui.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    LoginThrottle,
    bind_host,
    hash_password,
    is_open_path,
    issue_token,
    lan_ready,
    load_or_create_secret,
    token_valid,
    verify_password,
)

PASSWORT = "sehr-geheim-123"


# ----------------------------------------------------------- Bausteine

def test_passwort_wird_nie_im_klartext_gespeichert():
    gespeichert = hash_password(PASSWORT)
    assert PASSWORT not in gespeichert
    assert gespeichert.startswith("pbkdf2_sha256$")


def test_gleiches_passwort_ergibt_verschiedene_ableitungen():
    """Zufaelliges Salz: Sonst verriete ein Vergleich zweier Dateien, dass
    dasselbe Passwort verwendet wird."""
    assert hash_password(PASSWORT) != hash_password(PASSWORT)


def test_pruefung_erkennt_richtig_und_falsch():
    gespeichert = hash_password(PASSWORT)
    assert verify_password(PASSWORT, gespeichert)
    assert not verify_password("falsch", gespeichert)
    assert not verify_password(PASSWORT + " ", gespeichert)


@pytest.mark.parametrize("gespeichert", ["", "quatsch", "md5$1$aa$bb", "pbkdf2_sha256$x$y$z"])
def test_unbrauchbare_ableitung_gilt_nie_als_richtig(gespeichert):
    assert not verify_password(PASSWORT, gespeichert)


def test_schluessel_bleibt_ueber_neustarts_gleich(tmp_path):
    """Sonst waere man nach jedem Programmstart wieder abgemeldet."""
    assert load_or_create_secret(tmp_path) == load_or_create_secret(tmp_path)


def test_token_ist_ohne_schluessel_nicht_faelschbar(tmp_path):
    schluessel = load_or_create_secret(tmp_path)
    token = issue_token(schluessel)
    assert token_valid(token, schluessel)
    assert not token_valid(token, b"x" * 48)


def test_veraendertes_token_wird_abgelehnt(tmp_path):
    schluessel = load_or_create_secret(tmp_path)
    token = issue_token(schluessel)
    assert not token_valid(token[:-3] + "abc", schluessel)
    assert not token_valid("", schluessel)
    assert not token_valid("ohne-punkt", schluessel)


def test_abgelaufenes_token_wird_abgelehnt(tmp_path):
    schluessel = load_or_create_secret(tmp_path)
    alt = issue_token(schluessel, time.time() - SESSION_MAX_AGE - 60)
    assert not token_valid(alt, schluessel)


def test_bremse_waechst_mit_den_fehlversuchen():
    bremse = LoginThrottle()
    verzoegerungen = [bremse.failed() for _ in range(5)]
    assert verzoegerungen == sorted(verzoegerungen)
    assert verzoegerungen[-1] > verzoegerungen[0]
    bremse.succeeded()
    assert bremse.delay == 0


@pytest.mark.parametrize("pfad", ["/anmelden", "/static/app.css", "/manifest.webmanifest",
                                  "/sw.js", "/icons/icon-192.png"])
def test_anmeldeseite_und_statisches_bleiben_offen(pfad):
    """Sonst laedt die Anmeldeseite ihr eigenes Stylesheet nicht."""
    assert is_open_path(pfad)


@pytest.mark.parametrize("pfad", ["/", "/screener/swing", "/watchlist", "/kurse"])
def test_alles_andere_ist_geschuetzt(pfad):
    assert not is_open_path(pfad)


# -------------------------------------------------------- Netzfreigabe

def test_netzfreigabe_ohne_passwort_wird_verweigert(settings):
    """Als Sperre, nicht als Hinweis: Ein Werkzeug, das die eigene Watchlist
    ungeschuetzt ins WLAN stellt, ist ein Fehler."""
    settings.ui.allow_lan = True
    bereit, meldung = lan_ready(settings)
    assert not bereit
    assert "Passwort" in meldung


def test_netzfreigabe_mit_passwort_ist_erlaubt(settings):
    settings.ui.allow_lan = True
    settings.ui.password_hash = hash_password(PASSWORT)
    assert lan_ready(settings)[0]


def test_ohne_netzfreigabe_keine_pruefung(settings):
    assert lan_ready(settings)[0]


def test_bindung_folgt_der_einstellung(settings):
    assert bind_host(settings) == "127.0.0.1"
    settings.ui.allow_lan = True
    assert bind_host(settings) == "0.0.0.0"


# ------------------------------------------------------- Im Zusammenspiel

@pytest.fixture
def geschuetzter_client(seeded, settings):
    settings.schedule.enabled = False
    settings.ui.password_hash = hash_password(PASSWORT)
    with TestClient(create_app(settings)) as client:
        yield client


def test_ohne_anmeldung_wird_umgeleitet(geschuetzter_client):
    antwort = geschuetzter_client.get("/screener/swing", follow_redirects=False)
    assert antwort.status_code == 303
    assert antwort.headers["location"].startswith("/anmelden")
    assert "weiter=" in antwort.headers["location"]


def test_anmeldeseite_ist_ohne_anmeldung_erreichbar(geschuetzter_client):
    antwort = geschuetzter_client.get("/anmelden")
    assert antwort.status_code == 200
    assert "Passwort" in antwort.text


def test_richtiges_passwort_meldet_an(geschuetzter_client):
    antwort = geschuetzter_client.post(
        "/anmelden", data={"passwort": PASSWORT, "weiter": "/watchlist"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    assert antwort.headers["location"] == "/watchlist"
    assert COOKIE_NAME in antwort.cookies
    assert geschuetzter_client.get("/").status_code == 200


def test_falsches_passwort_meldet_nicht_an(geschuetzter_client):
    antwort = geschuetzter_client.post(
        "/anmelden", data={"passwort": "daneben"}, follow_redirects=False)
    assert antwort.status_code == 303
    assert "fehler=1" in antwort.headers["location"]
    assert COOKIE_NAME not in antwort.cookies


def test_weiterleitung_nur_auf_eigene_pfade(geschuetzter_client):
    """Sonst liesse sich die Anmeldung nutzen, um auf eine fremde Adresse
    weiterzuleiten."""
    for ziel in ["https://example.invalid/", "//example.invalid/", "javascript:alert(1)"]:
        antwort = geschuetzter_client.post(
            "/anmelden", data={"passwort": PASSWORT, "weiter": ziel},
            follow_redirects=False)
        assert antwort.headers["location"] == "/", ziel


def test_abmelden_entzieht_den_zugang(geschuetzter_client):
    geschuetzter_client.post("/anmelden", data={"passwort": PASSWORT})
    assert geschuetzter_client.get("/").status_code == 200

    geschuetzter_client.post("/abmelden", follow_redirects=False)
    antwort = geschuetzter_client.get("/", follow_redirects=False)
    assert antwort.status_code == 303


def test_ohne_passwort_gibt_es_keinen_schutz(client):
    """Auf 127.0.0.1 kommt ohnehin nur der eigene Rechner dran - eine
    Anmeldung waere dort nur Reibung."""
    assert client.get("/").status_code == 200
    assert client.get("/anmelden", follow_redirects=False).status_code == 303


def test_statische_dateien_bleiben_ohne_anmeldung_erreichbar(geschuetzter_client):
    assert geschuetzter_client.get("/static/app.css").status_code == 200


def test_abmeldeknopf_nur_bei_gesetztem_passwort(geschuetzter_client, client):
    geschuetzter_client.post("/anmelden", data={"passwort": PASSWORT})
    assert "/abmelden" in geschuetzter_client.get("/").text
    assert "/abmelden" not in client.get("/").text


# ----------------------------------------------- Verschluesselte Verbindung

def test_zertifikat_der_stelle_ist_ohne_anmeldung_abrufbar(seeded, settings, tmp_path):
    """Ohne die Stelle kommt das Handy gar nicht erst bis zur Anmeldeseite."""
    from trading_tool.tls import ensure_certificate

    ensure_certificate(settings.data_dir)
    settings.schedule.enabled = False
    settings.ui.password_hash = hash_password(PASSWORT)
    with TestClient(create_app(settings)) as client:
        antwort = client.get("/ca.crt")
        assert antwort.status_code == 200
        assert antwort.headers["content-type"] == "application/x-x509-ca-cert"
        assert antwort.content.startswith(b"-----BEGIN CERTIFICATE-----")


def test_ohne_zertifikat_leitet_der_abruf_weiter(geschuetzter_client):
    antwort = geschuetzter_client.get("/ca.crt", follow_redirects=False)
    assert antwort.status_code == 303


def test_plaetzchen_ist_ueber_http_nicht_als_sicher_markiert(geschuetzter_client):
    """Auf HTTP waere 'Secure' kontraproduktiv - der Browser wuerde das
    Plaetzchen dann nie senden."""
    antwort = geschuetzter_client.post(
        "/anmelden", data={"passwort": PASSWORT}, follow_redirects=False)
    assert "secure" not in antwort.headers.get("set-cookie", "").lower()


def test_plaetzchen_ist_ueber_https_als_sicher_markiert(seeded, settings):
    settings.schedule.enabled = False
    settings.ui.password_hash = hash_password(PASSWORT)
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        antwort = client.post("/anmelden", data={"passwort": PASSWORT}, follow_redirects=False)
        kopfzeile = antwort.headers.get("set-cookie", "").lower()
        assert "secure" in kopfzeile
        assert "httponly" in kopfzeile
