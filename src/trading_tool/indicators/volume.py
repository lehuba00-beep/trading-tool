"""Volumenindikatoren."""

from __future__ import annotations

import pandas as pd


def relative_volume(volume: pd.Series, lookback: int = 20) -> pd.Series:
    """Volumen im Verhaeltnis zum Durchschnitt der Vorperioden.

    Der aktuelle Balken ist aus dem Durchschnitt ausgeschlossen, sonst
    verwaessert ein Volumenausschlag seinen eigenen Vergleichsmassstab.
    """
    baseline = volume.shift(1).rolling(lookback, min_periods=max(5, lookback // 2)).mean()
    return volume / baseline.where(baseline != 0)


def turnover(close: pd.Series, volume: pd.Series, lookback: int = 20) -> pd.Series:
    """Durchschnittlicher Umsatz je Balken in Waehrungseinheiten.

    Das Liquiditaetsmass, auf das es ankommt: 100.000 gehandelte Stueck eines
    Pennystocks sind etwas anderes als 100.000 Stueck eines 200-Euro-Titels.
    """
    return (close * volume).rolling(lookback, min_periods=max(5, lookback // 2)).mean()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance-Volume."""
    direction = close.diff().pipe(lambda s: s.gt(0).astype(int) - s.lt(0).astype(int))
    return (direction * volume).fillna(0.0).cumsum()
