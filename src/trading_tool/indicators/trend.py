"""Trendindikatoren.

Alle Funktionen nehmen und liefern pandas-Objekte mit dem Index der Kursreihe
und rechnen vektorisiert. Keine Schleifen ueber Balken - das haelt einen
Screening-Lauf ueber mehrere hundert Titel im Sekundenbereich.
"""

from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilders Glaettung - Grundlage von RSI, ATR und ADX.

    Entspricht einem EMA mit alpha = 1/period, nicht 2/(period+1). Wer das
    verwechselt, bekommt Werte, die anderen Charttools aehneln, aber nicht
    gleichen.
    """
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Liefert (MACD-Linie, Signallinie, Histogramm)."""
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return macd_line, signal_line, macd_line - signal_line


def directional_movement(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Liefert (+DI, -DI, ADX) nach Wilder."""
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    atr_ = wilder_smooth(true_range, period)
    plus_di = 100 * wilder_smooth(plus_dm, period) / atr_
    minus_di = 100 * wilder_smooth(minus_dm, period) / atr_

    di_sum = plus_di + minus_di
    dx = 100 * (plus_di - minus_di).abs() / di_sum.where(di_sum != 0)
    adx_ = wilder_smooth(dx.fillna(0.0), period)
    return plus_di, minus_di, adx_


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return directional_movement(high, low, close, period)[2]


def slope_pct(series: pd.Series, lookback: int) -> pd.Series:
    """Relative Steigung ueber ``lookback`` Balken in Prozent.

    Fuer die Frage 'steigt die 200-Tage-Linie?' - ein Kurs ueber einer fallenden
    Linie ist etwas anderes als einer ueber einer steigenden.
    """
    past = series.shift(lookback)
    return (series - past) / past.abs().where(past != 0) * 100
