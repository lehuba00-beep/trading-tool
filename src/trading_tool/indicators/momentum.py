"""Momentum- und Staerkeindikatoren."""

from __future__ import annotations

import pandas as pd

from .trend import wilder_smooth


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index nach Wilder."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = wilder_smooth(gain, period)
    avg_loss = wilder_smooth(loss, period)

    rs = avg_gain / avg_loss.where(avg_loss != 0)
    out = 100 - (100 / (1 + rs))
    # Reine Gewinnserie: avg_loss = 0 -> RSI 100 (nicht NaN).
    return out.where(avg_loss != 0, 100.0).where(avg_gain.notna())


def roc(series: pd.Series, period: int) -> pd.Series:
    """Rate of Change in Prozent."""
    past = series.shift(period)
    return (series - past) / past.abs().where(past != 0) * 100


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14, smooth: int = 3
) -> tuple[pd.Series, pd.Series]:
    lowest = low.rolling(period, min_periods=period).min()
    highest = high.rolling(period, min_periods=period).max()
    span = (highest - lowest).where(lambda s: s != 0)
    k = 100 * (close - lowest) / span
    return k, k.rolling(smooth, min_periods=smooth).mean()


def momentum_12_1(series: pd.Series, months: int = 12, skip_months: int = 1) -> pd.Series:
    """Klassisches 12-1-Momentum: Rendite ueber 12 Monate ohne den letzten Monat.

    Der ausgelassene Monat entfernt die kurzfristige Umkehrbewegung, die das
    reine 12-Monats-Momentum systematisch verwaessert. Gerechnet wird in
    Handelstagen (21 je Monat).
    """
    start = series.shift(months * 21)
    end = series.shift(skip_months * 21)
    return (end - start) / start.abs().where(start != 0) * 100


def distance_to_high(series: pd.Series, period: int = 252) -> pd.Series:
    """Abstand zum Hoch der letzten ``period`` Balken in Prozent (positiv = darunter)."""
    highest = series.rolling(period, min_periods=max(20, period // 4)).max()
    return (highest - series) / highest.where(highest != 0) * 100


def relative_strength(series: pd.Series, benchmark: pd.Series, period: int) -> pd.Series:
    """Ueberrendite gegenueber einer Vergleichsreihe in Prozentpunkten.

    Den Index zu schlagen ist der eigentliche Zweck der Titelauswahl; eine
    absolute Rendite von 5 % ist in einem Markt, der 12 % gemacht hat, schwach.
    """
    aligned = benchmark.reindex(series.index).ffill()
    return roc(series, period) - roc(aligned, period)
