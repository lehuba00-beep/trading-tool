"""Transportverschluesselung fuer den Zugriff aus dem Heimnetz.

Wichtig zur Einordnung: Verschluesselung schuetzt den Uebertragungsweg. Sie
ersetzt kein VPN - eine Portfreigabe setzt die Anwendung weiterhin dem
gesamten Internet aus, dann eben verschluesselt.
"""

from __future__ import annotations

import datetime as dt

import pytest
from cryptography import x509

from trading_tool.tls import (
    RENEW_BEFORE_DAYS,
    SERVER_DAYS,
    certificate_covers,
    ensure_certificate,
    local_addresses,
    paths,
)
from trading_tool.ui.auth import hash_password, tls_active


def _lade(pfad):
    return x509.load_pem_x509_certificate(pfad.read_bytes())


def _san(zertifikat):
    return zertifikat.extensions.get_extension_for_class(x509.SubjectAlternativeName).value


def test_zertifikat_wird_erzeugt(tmp_path):
    ziel = ensure_certificate(tmp_path)
    assert ziel.complete
    assert (tmp_path / "tls" / "ca.key").exists()


def test_server_wird_von_der_eigenen_stelle_signiert(tmp_path):
    ziel = ensure_certificate(tmp_path)
    assert _lade(ziel.server_cert).issuer == _lade(ziel.ca_cert).subject


def test_stelle_ist_als_solche_gekennzeichnet_der_server_nicht(tmp_path):
    """Sonst koennte das Serverzertifikat seinerseits Zertifikate ausstellen."""
    ziel = ensure_certificate(tmp_path)
    ca = _lade(ziel.ca_cert).extensions.get_extension_for_class(x509.BasicConstraints).value
    server = _lade(ziel.server_cert).extensions.get_extension_for_class(x509.BasicConstraints).value
    assert ca.ca is True
    assert server.ca is False


def test_zertifikat_deckt_localhost_und_die_netzadresse_ab(tmp_path):
    """Browser ignorieren den Common Name seit Jahren - allein diese Liste zaehlt."""
    ziel = ensure_certificate(tmp_path)
    san = _san(_lade(ziel.server_cert))
    namen, adressen = local_addresses()
    assert "localhost" in san.get_values_for_type(x509.DNSName)
    assert "127.0.0.1" in {str(a) for a in san.get_values_for_type(x509.IPAddress)}
    assert set(namen) <= set(san.get_values_for_type(x509.DNSName))


def test_laufzeit_bleibt_im_rahmen_der_browser(tmp_path):
    """Ueber 398 Tage lehnen Browser Serverzertifikate ab."""
    zertifikat = _lade(ensure_certificate(tmp_path).server_cert)
    tage = (zertifikat.not_valid_after_utc - zertifikat.not_valid_before_utc).days
    assert tage == SERVER_DAYS
    assert tage < 398


def test_zweiter_aufruf_stellt_nichts_neu_aus(tmp_path):
    erst = ensure_certificate(tmp_path).server_cert.read_bytes()
    assert ensure_certificate(tmp_path).server_cert.read_bytes() == erst


def test_erzwungene_erneuerung_behaelt_die_stelle(tmp_path):
    """Der Kern des Aufbaus: Die einmal auf dem Handy hinterlegte Stelle muss
    eine Neuausstellung ueberleben - sonst waere jedes Mal wieder eine
    Warnung faellig."""
    ziel = ensure_certificate(tmp_path)
    server_vorher = ziel.server_cert.read_bytes()
    ca_vorher = ziel.ca_cert.read_bytes()

    ensure_certificate(tmp_path, force=True)
    assert ziel.server_cert.read_bytes() != server_vorher
    assert ziel.ca_cert.read_bytes() == ca_vorher


def test_fremde_adresse_gilt_als_nicht_abgedeckt(tmp_path):
    """Nach einem Adresswechsel aus dem Router muss neu ausgestellt werden."""
    ziel = ensure_certificate(tmp_path)
    assert not certificate_covers(ziel.server_cert, [], ["10.99.99.99"])


def test_aktuelle_adressen_gelten_als_abgedeckt(tmp_path):
    ziel = ensure_certificate(tmp_path)
    namen, adressen = local_addresses()
    assert certificate_covers(ziel.server_cert, namen, adressen)


def test_fehlendes_zertifikat_gilt_als_nicht_abgedeckt(tmp_path):
    assert not certificate_covers(tmp_path / "gibtsnicht.crt", [], [])


def test_unlesbares_zertifikat_gilt_als_nicht_abgedeckt(tmp_path):
    kaputt = tmp_path / "kaputt.crt"
    kaputt.write_bytes(b"kein Zertifikat")
    assert not certificate_covers(kaputt, [], [])


def test_bald_ablaufendes_zertifikat_wird_erneuert(tmp_path, monkeypatch):
    import trading_tool.tls as modul

    ziel = ensure_certificate(tmp_path)
    namen, adressen = local_addresses()
    assert certificate_covers(ziel.server_cert, namen, adressen)

    # Die Uhr kurz vor den Erneuerungszeitpunkt schieben
    echt = modul.dt.datetime
    ziel_zeit = echt.now(dt.UTC) + dt.timedelta(days=SERVER_DAYS - RENEW_BEFORE_DAYS + 1)

    class Verschoben(echt):
        @classmethod
        def now(cls, tz=None):
            return ziel_zeit

    monkeypatch.setattr(modul.dt, "datetime", Verschoben)
    assert not certificate_covers(ziel.server_cert, namen, adressen)


def test_privater_schluessel_liegt_nicht_offen(tmp_path):
    import os
    import sys

    ziel = ensure_certificate(tmp_path)
    if sys.platform == "win32":
        pytest.skip("Windows kennt die Rechte so nicht")
    rechte = os.stat(ziel.server_key).st_mode & 0o777
    assert rechte == 0o600, "der private Schluessel darf nur dem Besitzer gehoeren"


def test_pfade_liegen_unter_dem_datenverzeichnis(tmp_path):
    ziel = paths(tmp_path)
    for pfad in (ziel.ca_cert, ziel.server_cert, ziel.server_key):
        assert tmp_path in pfad.parents


# ------------------------------------------------- Wann ist TLS ueberhaupt an

def test_ohne_netzfreigabe_keine_verschluesselung(settings):
    """Auf 127.0.0.1 verlaesst kein Paket den Rechner - TLS braechte dort
    keinen Schutz, nur eine Zertifikatswarnung."""
    assert not tls_active(settings)


def test_mit_netzfreigabe_ist_verschluesselung_an(settings):
    settings.ui.allow_lan = True
    settings.ui.password_hash = hash_password("test-passwort-123")
    assert tls_active(settings)


def test_verschluesselung_laesst_sich_abschalten(settings):
    settings.ui.allow_lan = True
    settings.ui.use_tls = False
    assert not tls_active(settings)
