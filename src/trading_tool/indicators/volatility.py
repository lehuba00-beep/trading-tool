"""Volatilitaets- und Spannbreitenindikatoren."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .trend import wilder_smooth


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return wilder_smooth(true_range(high, low, close), period)


def atr_pct(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ATR in Prozent des Kurses - erst das macht Titel vergleichbar."""
    return atr(high, low, close, period) / close.where(close != 0) * 100


def bollinger(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = series.rolling(period, min_periods=period).mean()
    std = series.rolling(period, min_periods=period).std(ddof=0)
    return mid - num_std * std, mid, mid + num_std * std


def bollinger_bandwidth(series: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series:
    lower, mid, upper = bollinger(series, period, num_std)
    return (upper - lower) / mid.where(mid != 0) * 100


def bandwidth_percentile(bandwidth: pd.Series, lookback: int = 126) -> pd.Series:
    """Perzentilrang der aktuellen Bandbreite im Rueckblickfenster (0-100).

    Niedrige Werte = Kontraktion. Auf Volatilitaetskontraktion folgt haeufig
    eine Expansion; die Richtung sagt der Squeeze allerdings nicht voraus.
    """
    return bandwidth.rolling(lookback, min_periods=max(20, lookback // 4)).rank(pct=True) * 100


def donchian(high: pd.Series, low: pd.Series, period: int = 20) -> tuple[pd.Series, pd.Series]:
    """Oberes und unteres Band der letzten ``period`` Balken - ohne den aktuellen.

    Der aktuelle Balken muss ausgeschlossen sein, sonst liegt der Kurs per
    Konstruktion nie ueber seinem eigenen Hoch und es gibt nie einen Ausbruch.
    """
    upper = high.shift(1).rolling(period, min_periods=period).max()
    lower = low.shift(1).rolling(period, min_periods=period).min()
    return upper, lower


def realized_volatility(series: pd.Series, period: int = 20, trading_days: int = 252) -> pd.Series:
    """Annualisierte Volatilitaet der logarithmischen Tagesrenditen in Prozent."""
    returns = np.log(series / series.shift(1))
    return returns.rolling(period, min_periods=period).std(ddof=0) * np.sqrt(trading_days) * 100


def rolling_max_drawdown(series: pd.Series, period: int = 126) -> pd.Series:
    """Groesster Rueckgang vom rollierenden Hoch im Fenster, in Prozent (positiv)."""
    peak = series.rolling(period, min_periods=max(20, period // 4)).max()
    return (peak - series) / peak.where(peak != 0) * 100
