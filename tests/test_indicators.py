"""Indikatoren gegen von Hand nachrechenbare Faelle.

Die Testfaelle sind bewusst so gewaehlt, dass sich das erwartete Ergebnis
ohne Bibliothek bestimmen laesst - sonst prueft der Test nur, dass sich der
Code nicht aendert, nicht dass er richtig rechnet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_tool import indicators as ind

from .conftest import make_series


def test_sma_ist_gleitender_mittelwert():
    series = pd.Series([1.0, 2, 3, 4, 5])
    assert ind.sma(series, 3).tolist()[2:] == [2.0, 3.0, 4.0]
    assert pd.isna(ind.sma(series, 3).iloc[1]), "vor dem Fenster darf kein Wert stehen"


def test_wilder_smoothing_nutzt_alpha_ein_durch_n():
    """Wilder glaettet mit alpha = 1/n, nicht mit 2/(n+1) wie ein klassischer EMA."""
    series = pd.Series([10.0] * 5 + [20.0])
    smoothed = ind.wilder_smooth(series, 5).iloc[-1]
    assert smoothed == pytest.approx(10 + (20 - 10) / 5)


def test_rsi_bei_reiner_gewinnserie_ist_hundert():
    steigend = pd.Series(np.arange(1, 40, dtype=float))
    assert ind.rsi(steigend, 14).iloc[-1] == pytest.approx(100.0)


def test_rsi_bei_reiner_verlustserie_ist_null():
    fallend = pd.Series(np.arange(40, 1, -1, dtype=float))
    assert ind.rsi(fallend, 14).iloc[-1] == pytest.approx(0.0)


def test_rsi_bleibt_im_wertebereich():
    values = ind.rsi(make_series(seed=7)["close"], 14).dropna()
    assert values.between(0, 100).all()


def test_true_range_beruecksichtigt_kursluecke():
    high = pd.Series([10.0, 12.0])
    low = pd.Series([9.0, 11.5])
    close = pd.Series([9.5, 12.0])
    # Gap nach oben: 12.0 - 9.5 = 2.5 schlaegt die Tagesspanne von 0.5
    assert ind.true_range(high, low, close).iloc[1] == pytest.approx(2.5)


def test_atr_ist_positiv():
    frame = make_series(seed=3)
    assert (ind.atr(frame["high"], frame["low"], frame["close"], 14).dropna() > 0).all()


def test_adx_liegt_zwischen_null_und_hundert():
    frame = make_series(seed=4)
    values = ind.adx(frame["high"], frame["low"], frame["close"], 14).dropna()
    assert values.between(0, 100).all()


def test_adx_ist_im_starken_trend_hoeher_als_im_seitwaerts():
    trend = make_series(n=400, drift=0.004, vol=0.004, seed=5)
    seitwaerts = make_series(n=400, drift=0.0, vol=0.004, seed=5)
    trend_adx = ind.adx(trend["high"], trend["low"], trend["close"]).iloc[-1]
    flat_adx = ind.adx(seitwaerts["high"], seitwaerts["low"], seitwaerts["close"]).iloc[-1]
    assert trend_adx > flat_adx


def test_donchian_schliesst_den_aktuellen_balken_aus():
    """Sonst laege der Kurs nie ueber seinem eigenen Hoch und es gaebe nie einen Ausbruch."""
    high = pd.Series([10.0] * 20 + [15.0])
    low = pd.Series([9.0] * 21
                    )
    upper, _ = ind.donchian(high, low, 20)
    assert upper.iloc[-1] == pytest.approx(10.0)


def test_relative_volume_schliesst_den_aktuellen_balken_aus():
    volume = pd.Series([100.0] * 20 + [300.0])
    assert ind.relative_volume(volume, 20).iloc[-1] == pytest.approx(3.0)


def test_roc_rechnet_prozent():
    series = pd.Series([100.0, 110.0])
    assert ind.roc(series, 1).iloc[-1] == pytest.approx(10.0)


def test_momentum_12_1_laesst_den_letzten_monat_aus():
    n = 300
    series = pd.Series(np.arange(100.0, 100.0 + n))
    # Ergebnis muss dem Abschnitt zwischen t-252 und t-21 entsprechen
    start = series.iloc[-1 - 252]
    end = series.iloc[-1 - 21]
    erwartet = (end - start) / start * 100
    assert ind.momentum_12_1(series).iloc[-1] == pytest.approx(erwartet)


def test_distance_to_high_ist_null_am_hoch():
    series = pd.Series(np.arange(1.0, 300.0))
    assert ind.distance_to_high(series, 252).iloc[-1] == pytest.approx(0.0)


def test_turnover_gewichtet_mit_dem_kurs():
    close = pd.Series([10.0] * 20)
    volume = pd.Series([1000.0] * 20)
    assert ind.turnover(close, volume, 20).iloc[-1] == pytest.approx(10_000.0)


def test_realized_volatility_steigt_mit_dem_rauschen():
    ruhig = ind.realized_volatility(make_series(vol=0.005, seed=8)["close"]).iloc[-1]
    wild = ind.realized_volatility(make_series(vol=0.03, seed=8)["close"]).iloc[-1]
    assert wild > ruhig * 2


def test_indikatoren_vertragen_kurze_reihen():
    """Am Reihenanfang darf kein Wert entstehen, aber auch keine Ausnahme fliegen."""
    frame = make_series(n=5, seed=9)
    assert ind.rsi(frame["close"], 14).isna().all()
    assert ind.adx(frame["high"], frame["low"], frame["close"], 14).isna().all()
