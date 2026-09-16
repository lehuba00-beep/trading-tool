"""Netzwerkpruefung.

Anlass: 'Die Website ist nicht erreichbar' auf dem Handy hat ein halbes
Dutzend moeglicher Ursachen - von 'Netzzugriff nie eingeschaltet' bis
'Windows-Firewall blockiert'. Statt raten zu lassen, geht der Befehl sie der
Reihe nach durch.
"""

from __future__ import annotations

import argparse
import socket

import pytest

from trading_tool.__main__ import _kann_binden, _laeuft_dort_die_anwendung, command_netcheck
from trading_tool.config import save_settings
from trading_tool.ui.auth import hash_password


@pytest.fixture
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_TOOL_DATA_DIR", str(tmp_path))
    return tmp_path


def _einrichten(tmp_path, netz: bool, passwort: bool = True, port: int = 0):
    from trading_tool.config import load_settings

    s = load_settings()
    s.ui.allow_lan = netz
    s.ui.password_hash = hash_password("test-passwort-123") if passwort else ""
    s.ui.port = port
    save_settings(s)
    return s


def test_abgeschalteter_netzzugriff_wird_als_ursache_genannt(daten, capsys):
    _einrichten(daten, netz=False)
    assert command_netcheck(argparse.Namespace()) == 1
    ausgabe = capsys.readouterr().out
    assert "Zugriff aus dem Heimnetz ist AUS" in ausgabe
    assert "passwort --netz" in ausgabe


def test_fehlendes_passwort_wird_genannt(daten, capsys):
    _einrichten(daten, netz=True, passwort=False)
    assert command_netcheck(argparse.Namespace()) == 1
    assert "Kein Passwort" in capsys.readouterr().out


def test_gleicher_befehl_steht_nur_einmal_in_der_liste(daten, capsys):
    """Ein Befehl behebt oft mehrere Befunde - dann soll er einmal dastehen."""
    _einrichten(daten, netz=False, passwort=False)
    command_netcheck(argparse.Namespace())
    liste = capsys.readouterr().out.split("Zu erledigen:")[1]
    assert liste.count("passwort --netz") == 1


def test_fehlendes_zertifikat_wird_genannt(daten, capsys):
    _einrichten(daten, netz=True)
    assert command_netcheck(argparse.Namespace()) == 1
    ausgabe = capsys.readouterr().out
    assert "kein Zertifikat" in ausgabe
    assert "zertifikat" in ausgabe


def test_vollstaendige_einrichtung_meldet_die_adresse(daten, capsys):
    from trading_tool.tls import ensure_certificate

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        frei = probe.getsockname()[1]

    _einrichten(daten, netz=True, port=frei)
    ensure_certificate(daten)
    assert command_netcheck(argparse.Namespace()) == 0

    ausgabe = capsys.readouterr().out
    assert "Alles in Ordnung" in ausgabe
    assert "https://" in ausgabe
    # Der haeufigste Rest: es liegt am Netz, nicht an der Anwendung
    assert "Gaeste-WLAN" in ausgabe
    assert "Isolation" in ausgabe


def test_hinweis_wenn_die_anwendung_gar_nicht_laeuft(daten, capsys):
    from trading_tool.tls import ensure_certificate

    # Ausdruecklich ein freier Port: Auf dem Vorgabeport koennte tatsaechlich
    # eine Anwendung laufen, und der Test pruefte dann das Gegenteil.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        frei = probe.getsockname()[1]

    _einrichten(daten, netz=True, port=frei)
    ensure_certificate(daten)
    command_netcheck(argparse.Namespace())
    assert "laeuft gerade nicht" in capsys.readouterr().out


def test_ausgabe_nennt_rechnername_als_alternative(daten, capsys):
    """Nach einem Adresswechsel aus dem Router hilft der Name weiter."""
    _einrichten(daten, netz=False)
    command_netcheck(argparse.Namespace())
    assert "Rechnername" in capsys.readouterr().out


# ------------------------------------------------------------- Bausteine

def test_freier_port_laesst_sich_binden():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        frei = probe.getsockname()[1]
    assert _kann_binden(frei)


def test_belegter_port_wird_erkannt():
    with socket.socket() as belegt:
        belegt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        belegt.bind(("0.0.0.0", 0))
        belegt.listen(1)
        assert not _kann_binden(belegt.getsockname()[1])


def test_fremdes_programm_gilt_nicht_als_die_anwendung():
    """Sonst waere 'Port belegt' nicht von 'laeuft schon' zu unterscheiden."""
    with socket.socket() as fremd:
        fremd.bind(("127.0.0.1", 0))
        fremd.listen(1)
        assert not _laeuft_dort_die_anwendung(fremd.getsockname()[1], "http")


def test_geschlossener_port_gilt_nicht_als_die_anwendung():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        zu = probe.getsockname()[1]
    assert not _laeuft_dort_die_anwendung(zu, "http")
