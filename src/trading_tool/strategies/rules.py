"""Regelbausteine.

Bewusst deklarativ statt frei auswertbarer Ausdruecke: Jede Regel ist eine
registrierte Funktion mit benannten Parametern. Das hat drei Gruende - die
Regeln sind einzeln testbar, die Oberflaeche kann sie als Formular darstellen,
und eine Konfigurationsdatei kann keinen beliebigen Code ausfuehren.

Jede Regel liefert eine **boolesche Zeitreihe** ueber die gesamte Kurshistorie,
nicht einen einzelnen Wahrheitswert. Das Screening liest davon den letzten
Wert, die Trefferquoten-Auswertung die ganze Reihe - beide nutzen damit
zwangslaeufig dieselbe Logik.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

import pandas as pd

from .context import IndicatorContext

RuleFn = Callable[..., tuple[pd.Series, str]]
REGISTRY: dict[str, RuleFn] = {}


class RuleConfigError(ValueError):
    """Unbekannte Regel oder unpassende Parameter in der Strategie-YAML."""


def rule(name: str) -> Callable[[RuleFn], RuleFn]:
    def wrap(fn: RuleFn) -> RuleFn:
        REGISTRY[name] = fn
        return fn

    return wrap


def evaluate(name: str, ctx: IndicatorContext, params: dict) -> tuple[pd.Series, str]:
    fn = REGISTRY.get(name)
    if fn is None:
        raise RuleConfigError(
            f"Unbekannte Regel '{name}'. Verfuegbar: {', '.join(sorted(REGISTRY))}"
        )
    signature = inspect.signature(fn)
    allowed = set(signature.parameters) - {"ctx"}
    unknown = set(params) - allowed
    if unknown:
        raise RuleConfigError(
            f"Regel '{name}': unbekannte Parameter {sorted(unknown)}. "
            f"Erlaubt: {sorted(allowed)}"
        )
    series, label = fn(ctx, **params)
    return series.fillna(False).astype(bool), label


def _cmp(series: pd.Series, threshold: float, op: str) -> pd.Series:
    return series.gt(threshold) if op == "gt" else series.lt(threshold)


def _crossed_up(fast: pd.Series, slow: pd.Series, within: int) -> pd.Series:
    """Kreuzung nach oben innerhalb der letzten ``within`` Balken.

    Ein Kreuzen ist ein Ereignis eines einzelnen Tages. Ohne Zeitfenster waere
    die Regel nur an genau einem Tag wahr und praktisch nie im Screening
    sichtbar.
    """
    cross = fast.gt(slow) & fast.shift(1).le(slow.shift(1))
    return cross.rolling(max(1, within), min_periods=1).max().astype(bool)


# ------------------------------------------------------------------- Trend

@rule("above_ma")
def _above_ma(ctx, ma: str = "ema", period: int = 50, on: str = "adj_close"):
    return ctx.adj_close.gt(ctx.ma(ma, period, on)), f"Kurs ueber {ma.upper()}({period})"


@rule("below_ma")
def _below_ma(ctx, ma: str = "ema", period: int = 50, on: str = "adj_close"):
    return ctx.adj_close.lt(ctx.ma(ma, period, on)), f"Kurs unter {ma.upper()}({period})"


@rule("ma_stack")
def _ma_stack(ctx, ma: str = "sma", periods: list[int] | None = None):
    """Kurs ueber der schnellen ueber der langsamen Linie - saubere Trendstruktur."""
    periods = periods or [50, 200]
    series = ctx.adj_close.gt(ctx.ma(ma, periods[0]))
    for fast, slow in zip(periods, periods[1:], strict=False):
        series &= ctx.ma(ma, fast).gt(ctx.ma(ma, slow))
    label = " > ".join([f"{ma.upper()}({p})" for p in periods])
    return series, f"Kurs > {label}"


@rule("ma_cross_up")
def _ma_cross_up(ctx, ma: str = "sma", fast: int = 50, slow: int = 200, within_days: int = 20):
    return (
        _crossed_up(ctx.ma(ma, fast), ctx.ma(ma, slow), within_days),
        f"{ma.upper()}({fast}) kreuzt {ma.upper()}({slow}) (<= {within_days} Tage)",
    )


@rule("ma_slope_up")
def _ma_slope_up(ctx, ma: str = "sma", period: int = 200, lookback: int = 21,
                 min_pct: float = 0.0):
    return (
        ctx.slope_pct(ma, period, lookback).gt(min_pct),
        f"{ma.upper()}({period}) steigend ueber {lookback} Tage",
    )


@rule("macd_cross_up")
def _macd_cross_up(ctx, fast: int = 12, slow: int = 26, signal: int = 9, within_days: int = 5):
    line, sig, _ = ctx.macd(fast, slow, signal)
    return (
        _crossed_up(line, sig, within_days),
        f"MACD({fast},{slow},{signal}) kreuzt Signallinie (<= {within_days} Tage)",
    )


@rule("macd_above_signal")
def _macd_above_signal(ctx, fast: int = 12, slow: int = 26, signal: int = 9):
    line, sig, _ = ctx.macd(fast, slow, signal)
    return line.gt(sig), f"MACD({fast},{slow}) ueber Signallinie"


@rule("adx_above")
def _adx_above(ctx, period: int = 14, threshold: float = 20.0):
    """Trendstaerke. Trennt Trend von Seitwaertsbewegung - ohne diesen Filter
    liefern Trendfolgeregeln in Seitwaertsmaerkten laufend Fehlsignale."""
    return ctx.adx(period).gt(threshold), f"ADX({period}) > {threshold:g}"


# ---------------------------------------------------------------- Momentum

@rule("rsi_below")
def _rsi_below(ctx, period: int = 2, threshold: float = 10.0):
    return ctx.rsi(period).lt(threshold), f"RSI({period}) < {threshold:g}"


@rule("rsi_above")
def _rsi_above(ctx, period: int = 14, threshold: float = 55.0):
    return ctx.rsi(period).gt(threshold), f"RSI({period}) > {threshold:g}"


@rule("rsi_between")
def _rsi_between(ctx, period: int = 14, low: float = 40.0, high: float = 60.0):
    series = ctx.rsi(period)
    return series.between(low, high), f"RSI({period}) zwischen {low:g} und {high:g}"


@rule("roc_above")
def _roc_above(ctx, period: int = 10, threshold: float = 0.0):
    return ctx.roc(period).gt(threshold), f"Momentum {period} Tage > {threshold:g} %"


@rule("momentum_12_1_above")
def _momentum_12_1_above(ctx, months: int = 12, skip_months: int = 1, threshold: float = 0.0):
    return (
        ctx.momentum_12_1(months, skip_months).gt(threshold),
        f"{months}-{skip_months}-Momentum > {threshold:g} %",
    )


@rule("relative_strength_above")
def _relative_strength_above(ctx, period: int = 126, threshold: float = 0.0):
    series = ctx.relative_strength(period)
    label = f"Ueberrendite {period} Tage > {threshold:g} Pp"
    if series is None:
        # Ohne Vergleichsreihe darf die Regel nicht stillschweigend als erfuellt
        # gelten - sonst waere der Score ohne Benchmark systematisch zu hoch.
        return ctx.falsy(), label + " (keine Vergleichsreihe)"
    return series.gt(threshold), label


@rule("distance_to_high_below")
def _distance_to_high_below(ctx, period: int = 252, max_pct: float = 10.0):
    return (
        ctx.distance_to_high(period).lt(max_pct),
        f"weniger als {max_pct:g} % unter {period}-Tage-Hoch",
    )


# -------------------------------------------------------- Ausbruch / Volumen

@rule("donchian_breakout")
def _donchian_breakout(ctx, period: int = 20):
    upper, _ = ctx.donchian(period)
    return ctx.close.gt(upper), f"Ausbruch ueber {period}-Tage-Hoch"


@rule("donchian_breakdown")
def _donchian_breakdown(ctx, period: int = 20):
    _, lower = ctx.donchian(period)
    return ctx.close.lt(lower), f"Bruch unter {period}-Tage-Tief"


@rule("relative_volume_above")
def _relative_volume_above(ctx, lookback: int = 20, factor: float = 1.5):
    return (
        ctx.relative_volume(lookback).gt(factor),
        f"Volumen ueber {factor:g}-fachem {lookback}-Tage-Schnitt",
    )


@rule("bollinger_squeeze")
def _bollinger_squeeze(ctx, period: int = 20, num_std: float = 2.0, lookback: int = 126,
                       max_percentile: float = 25.0):
    """Volatilitaetskontraktion. Sagt eine Ausdehnung voraus, aber nicht deren
    Richtung - deshalb nie allein, sondern nur mit einer Richtungsregel."""
    return (
        ctx.bandwidth_pct(period, num_std, lookback).lt(max_percentile),
        f"Bollinger-Kontraktion (unter {max_percentile:g}. Perzentil)",
    )


@rule("volatility_below")
def _volatility_below(ctx, period: int = 20, max_pct: float = 40.0):
    return (
        ctx.realized_vol(period).lt(max_pct),
        f"Volatilitaet ({period} Tage) unter {max_pct:g} % p.a.",
    )


@rule("atr_pct_between")
def _atr_pct_between(ctx, period: int = 14, low: float = 1.0, high: float = 8.0):
    """Bewegungsspielraum. Zu ruhig heisst kein Weg, zu wild heisst der Stop
    wird von normalem Rauschen ausgeloest."""
    return (
        ctx.atr_pct(period).between(low, high),
        f"ATR({period}) zwischen {low:g} und {high:g} % des Kurses",
    )


@rule("pullback_from_high")
def _pullback_from_high(ctx, period: int = 252, min_pct: float = 3.0, max_pct: float = 15.0):
    return (
        ctx.distance_to_high(period).between(min_pct, max_pct),
        f"Ruecksetzer {min_pct:g}-{max_pct:g} % unter {period}-Tage-Hoch",
    )


@rule("close_above_open")
def _close_above_open(ctx, days: int = 1):
    series = ctx.close.gt(ctx.open)
    if days > 1:
        series = series.rolling(days, min_periods=days).min().astype(bool)
    return series, f"{days} Tag(e) mit Schluss ueber Eroeffnung"


def available_rules() -> list[str]:
    return sorted(REGISTRY)
