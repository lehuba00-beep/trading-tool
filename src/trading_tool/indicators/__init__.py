"""Indikatorbibliothek.

Bewusst selbst implementiert statt TA-Lib (C-Build unter Windows) oder
pandas-ta (Wartungsstand). Der Umfang ist ueberschaubar und gegen
Referenzwerte pruefbar - siehe tests/test_indicators.py.
"""

from .momentum import (
    distance_to_high,
    momentum_12_1,
    relative_strength,
    roc,
    rsi,
    stochastic,
)
from .trend import adx, directional_movement, ema, macd, slope_pct, sma, wilder_smooth
from .volatility import (
    atr,
    atr_pct,
    bandwidth_percentile,
    bollinger,
    bollinger_bandwidth,
    donchian,
    realized_volatility,
    rolling_max_drawdown,
    true_range,
)
from .volume import obv, relative_volume, turnover

__all__ = [
    "adx", "directional_movement", "ema", "macd", "slope_pct", "sma", "wilder_smooth",
    "distance_to_high", "momentum_12_1", "relative_strength", "roc", "rsi", "stochastic",
    "atr", "atr_pct", "bandwidth_percentile", "bollinger", "bollinger_bandwidth",
    "donchian", "realized_volatility", "rolling_max_drawdown", "true_range",
    "obv", "relative_volume", "turnover",
]
