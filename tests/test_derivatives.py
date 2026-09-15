"""Hebel- und Barrierenmathematik."""

from __future__ import annotations

import pytest

from trading_tool.derivatives import (
    barrier_from_distance,
    leverage_from_barrier,
    leverage_hint,
    loss_at_stop_pct,
    products_for,
)
from trading_tool.domain.enums import Direction, Horizon


def test_hebel_ist_der_kehrwert_des_schwellenabstands():
    """Der zentrale Zusammenhang: 10 % Abstand entsprechen Hebel 10."""
    assert leverage_from_barrier(100.0, 90.0) == pytest.approx(10.0)
    assert leverage_from_barrier(100.0, 95.0) == pytest.approx(20.0)


def test_schwelle_aus_abstand_beachtet_die_richtung():
    assert barrier_from_distance(100.0, 6.0, Direction.LONG) == pytest.approx(94.0)
    assert barrier_from_distance(100.0, 6.0, Direction.SHORT) == pytest.approx(106.0)


def test_hinweis_leitet_hebel_aus_dem_stop_ab():
    hinweis = leverage_hint(price=100.0, stop=96.0)
    assert hinweis.stop_distance_pct == pytest.approx(4.0)
    assert hinweis.min_barrier_distance_pct == pytest.approx(6.0)  # 4 % * Puffer 1,5
    assert hinweis.max_leverage == pytest.approx(16.7, abs=0.1)
    assert hinweis.suggested_barrier == pytest.approx(94.0)


def test_engerer_stop_erlaubt_mehr_hebel():
    eng = leverage_hint(100.0, 98.0).max_leverage
    weit = leverage_hint(100.0, 90.0).max_leverage
    assert eng > weit


def test_verlust_bei_stop_beruecksichtigt_den_hebel():
    """Bei Hebel 10 und 4 % Stop sind 40 % der Position weg, nicht 4 %."""
    assert loss_at_stop_pct(10.0, 4.0) == pytest.approx(40.0)


def test_verlust_ist_auf_totalverlust_begrenzt():
    assert loss_at_stop_pct(30.0, 10.0) == 100.0


def test_unsinnige_eingaben_liefern_keinen_hinweis():
    assert leverage_hint(0.0, 10.0) is None
    assert leverage_hint(100.0, 100.0) is None


def test_langfristige_signale_bekommen_keine_hebelprodukte():
    """Hebelprodukte sind fuer Haltedauern ab sechs Monaten nicht das Vehikel."""
    assert products_for(Horizon.LONG) == []


def test_faktorzertifikate_nur_bei_bestaetigtem_trend():
    schwach = [p["key"] for p in products_for(Horizon.SHORT, adx=15)]
    stark = [p["key"] for p in products_for(Horizon.SHORT, adx=30)]
    assert "faktor" not in schwach
    assert "faktor" in stark


def test_jeder_produkttyp_nennt_sein_hauptrisiko():
    for produkt in products_for(Horizon.SHORT, adx=30):
        assert produkt["hinweis"], produkt["key"]
