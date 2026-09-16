"""Portwahl.

Auf dem Rechner selbst ist ein wechselnder Port folgenlos - der Browser wird
ja mitgestartet. Vom Handy aus muesste man die Adresse nach jedem Start neu
nachschlagen, deshalb dort ein fester Port.
"""

from __future__ import annotations

import socket

from trading_tool.__main__ import _free_port
from trading_tool.config import DEFAULT_LAN_PORT, Settings


def test_ohne_netzzugriff_wird_ein_freier_port_gewaehlt(settings):
    assert settings.ui.preferred_port() == 0


def test_mit_netzzugriff_gilt_der_feste_port(settings):
    settings.ui.allow_lan = True
    assert settings.ui.preferred_port() == DEFAULT_LAN_PORT


def test_eigene_vorgabe_hat_immer_vorrang(settings):
    settings.ui.port = 9000
    assert settings.ui.preferred_port() == 9000
    settings.ui.allow_lan = True
    assert settings.ui.preferred_port() == 9000


def test_freier_wunschport_wird_genommen():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        frei = probe.getsockname()[1]
    port, ausgewichen = _free_port(frei)
    assert port == frei
    assert not ausgewichen


def test_belegter_port_wird_gemeldet():
    """Still auszuweichen waere das Schlimmste: Das Lesezeichen auf dem Handy
    zeigt dann ins Leere, ohne dass jemand erfaehrt, warum."""
    with socket.socket() as belegt:
        belegt.bind(("127.0.0.1", 0))
        belegt.listen(1)
        genommen = belegt.getsockname()[1]

        port, ausgewichen = _free_port(genommen)
        assert port != genommen
        assert ausgewichen is True


def test_ohne_wunsch_wird_nicht_von_ausweichen_gesprochen():
    port, ausgewichen = _free_port(0)
    assert port > 0
    assert not ausgewichen


def test_vorgabeport_ist_der_uebliche_ausweichport():
    """8443 ist die gaengige Alternative zu 443 und kollidiert selten."""
    assert DEFAULT_LAN_PORT == 8443


def test_einstellung_ueberlebt_das_speichern(tmp_path):
    import os

    from trading_tool.config import load_settings, save_settings
    os.environ["TRADING_TOOL_DATA_DIR"] = str(tmp_path)
    try:
        s = Settings(data_dir=tmp_path)
        s.ui.allow_lan = True
        s.ui.port = DEFAULT_LAN_PORT
        save_settings(s)
        neu = load_settings()
        assert neu.ui.port == DEFAULT_LAN_PORT
        assert neu.ui.allow_lan is True
    finally:
        os.environ.pop("TRADING_TOOL_DATA_DIR", None)
