"""Rechenkontext einer Kursreihe.

Haelt die OHLCV-Reihe und berechnet Indikatoren auf Abruf - jeden genau einmal.
Mehrere Regeln greifen auf dieselben Zwischenergebnisse zu (die EMA(50) taucht
in fast jedem Profil auf); ohne Zwischenspeicher wuerde ein Screening-Lauf ein
Vielfaches der noetigen Arbeit leisten.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from .. import indicators as ind


class IndicatorContext:
    def __init__(self, frame: pd.DataFrame, benchmark: pd.Series | None = None) -> None:
        self.frame = frame
        self.benchmark = benchmark
        self._cache: dict[tuple, pd.Series] = {}

    # Rohreihen ------------------------------------------------------------
    @property
    def open(self) -> pd.Series:
        return self.frame["open"]

    @property
    def high(self) -> pd.Series:
        return self.frame["high"]

    @property
    def low(self) -> pd.Series:
        return self.frame["low"]

    @property
    def close(self) -> pd.Series:
        """Roher Schlusskurs - fuer Kursniveaus, Stops und Anzeige."""
        return self.frame["close"]

    @property
    def adj_close(self) -> pd.Series:
        """Bereinigter Schlusskurs - Grundlage aller Indikatoren.

        Ohne Bereinigung erzeugt jeder Aktiensplit einen Kurssprung, den jeder
        Momentumindikator als echtes Signal liest.
        """
        return self.frame["adj_close"]

    @property
    def volume(self) -> pd.Series:
        return self.frame["volume"]

    @property
    def index(self) -> pd.Index:
        return self.frame.index

    def _memo(self, key: tuple, fn: Callable[[], pd.Series]) -> pd.Series:
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # Indikatoren ----------------------------------------------------------
    def ma(self, kind: str, period: int, on: str = "adj_close") -> pd.Series:
        series = getattr(self, on)
        fn = ind.ema if kind.lower() == "ema" else ind.sma
        return self._memo(("ma", kind, period, on), lambda: fn(series, period))

    def rsi(self, period: int) -> pd.Series:
        return self._memo(("rsi", period), lambda: ind.rsi(self.adj_close, period))

    def roc(self, period: int) -> pd.Series:
        return self._memo(("roc", period), lambda: ind.roc(self.adj_close, period))

    def macd(self, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        key = ("macd", fast, slow, signal)
        if key not in self._cache:
            line, sig, hist = ind.macd(self.adj_close, fast, slow, signal)
            self._cache[key] = line
            self._cache[(*key, "signal")] = sig
            self._cache[(*key, "hist")] = hist
        return self._cache[key], self._cache[(*key, "signal")], self._cache[(*key, "hist")]

    def adx(self, period: int) -> pd.Series:
        return self._memo(("adx", period), lambda: ind.adx(self.high, self.low, self.close, period))

    def atr(self, period: int) -> pd.Series:
        return self._memo(("atr", period), lambda: ind.atr(self.high, self.low, self.close, period))

    def atr_pct(self, period: int) -> pd.Series:
        return self._memo(
            ("atr_pct", period), lambda: ind.atr_pct(self.high, self.low, self.close, period)
        )

    def donchian(self, period: int) -> tuple[pd.Series, pd.Series]:
        key = ("donchian", period)
        if key not in self._cache:
            upper, lower = ind.donchian(self.high, self.low, period)
            self._cache[key] = upper
            self._cache[(*key, "lower")] = lower
        return self._cache[key], self._cache[(*key, "lower")]

    def bandwidth_pct(self, period: int, num_std: float, lookback: int) -> pd.Series:
        return self._memo(
            ("bwpct", period, num_std, lookback),
            lambda: ind.bandwidth_percentile(
                ind.bollinger_bandwidth(self.adj_close, period, num_std), lookback
            ),
        )

    def relative_volume(self, lookback: int) -> pd.Series:
        return self._memo(("rvol", lookback), lambda: ind.relative_volume(self.volume, lookback))

    def turnover(self, lookback: int) -> pd.Series:
        return self._memo(
            ("turnover", lookback), lambda: ind.turnover(self.close, self.volume, lookback)
        )

    def distance_to_high(self, period: int) -> pd.Series:
        return self._memo(
            ("dist_high", period), lambda: ind.distance_to_high(self.adj_close, period)
        )

    def momentum_12_1(self, months: int, skip: int) -> pd.Series:
        return self._memo(
            ("mom", months, skip), lambda: ind.momentum_12_1(self.adj_close, months, skip)
        )

    def realized_vol(self, period: int) -> pd.Series:
        return self._memo(
            ("rvola", period), lambda: ind.realized_volatility(self.adj_close, period)
        )

    def slope_pct(self, kind: str, period: int, lookback: int) -> pd.Series:
        return self._memo(
            ("slope", kind, period, lookback),
            lambda: ind.slope_pct(self.ma(kind, period), lookback),
        )

    def relative_strength(self, period: int) -> pd.Series | None:
        """Ueberrendite gegenueber der Vergleichsreihe. None, wenn keine vorliegt."""
        if self.benchmark is None or self.benchmark.empty:
            return None
        return self._memo(
            ("rs", period), lambda: ind.relative_strength(self.adj_close, self.benchmark, period)
        )

    def falsy(self) -> pd.Series:
        return pd.Series(False, index=self.index)
