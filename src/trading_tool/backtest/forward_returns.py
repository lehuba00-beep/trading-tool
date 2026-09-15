"""Auswertung der Signalguete ueber Vorwaertsrenditen.

Keine Backtest-Engine mit Orderbuch, Gebuehren und Positionsverwaltung -
sondern die schlichte Frage: Was ist nach einem Signal historisch passiert,
und war das besser als ein beliebiger Tag im selben Zeitraum?

Die Vergleichsgruppe ist der entscheidende Teil. Eine Trefferquote von 60 %
klingt gut, ist aber wertlos, wenn ein zufaellig gewaehlter Einstieg im selben
Zeitraum auf 58 % kommt.

Drei Verzerrungen, die bewusst behandelt bzw. offengelegt werden:

* **Vorgriff auf die Zukunft.** Das Signal entsteht auf dem Schlusskurs; der
  Einstieg erfolgt fruehestens zur Eroeffnung des Folgetages.
* **Ueberlappende Signale.** Loest eine Regel an fuenf Tagen hintereinander
  aus, waeren das fuenf fast identische Beobachtungen. Gezaehlt wird deshalb
  nur ein Signal je Haltedauer und Titel.
* **Ueberlebensverzerrung.** Delistete Titel fehlen in allen kostenlosen
  Quellen. Das laesst sich hier nicht beheben, nur benennen - die Ergebnisse
  sind dadurch systematisch zu optimistisch.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..strategies.base import Strategy
from ..strategies.context import IndicatorContext

log = logging.getLogger(__name__)

# Unter dieser Anzahl Beobachtungen ist jede Quote Zufall.
MIN_SIGNALS_FOR_STATS = 20


def forward_return(frame: pd.DataFrame, holding_days: int) -> pd.Series:
    """Rendite in Prozent: Einstieg zur Eroeffnung t+1, Ausstieg zum Schluss t+1+n."""
    entry = frame["open"].shift(-1)
    exit_ = frame["close"].shift(-(1 + holding_days))
    return (exit_ - entry) / entry.where(entry != 0) * 100


def _non_overlapping(positions: np.ndarray, holding_days: int) -> list[int]:
    """Nur ein Signal je Haltedauer - sonst zaehlt derselbe Move mehrfach."""
    kept: list[int] = []
    blocked_until = -1
    for position in positions:
        if position > blocked_until:
            kept.append(int(position))
            blocked_until = position + holding_days
    return kept


def evaluate_instrument(
    strategy: Strategy, frame: pd.DataFrame, benchmark: pd.Series | None = None
) -> tuple[list[float], list[float]]:
    """Liefert (Renditen nach Signal, Renditen aller vergleichbaren Tage)."""
    if len(frame) < strategy.universe.min_history_days + strategy.risk.max_holding_days + 5:
        return [], []

    ctx = IndicatorContext(frame, benchmark)
    evaluation = strategy.evaluate(ctx)
    holding = strategy.risk.max_holding_days
    returns = forward_return(frame, holding)

    usable = returns.notna().to_numpy()
    # Vergleichsgruppe nur ueber den Bereich, in dem auch Signale entstehen
    # koennten - sonst vergleicht man verschiedene Zeitraeume miteinander.
    warmup = strategy.universe.min_history_days
    window = np.zeros(len(frame), dtype=bool)
    window[warmup:] = True
    window &= usable

    eligible = evaluation.eligible.to_numpy() & window
    positions = np.flatnonzero(eligible)
    kept = _non_overlapping(positions, holding)

    values = returns.to_numpy()
    return [float(values[p]) for p in kept], [float(v) for v in values[window]]


def summarise(signal_returns: list[float], baseline_returns: list[float]) -> dict:
    signals = np.asarray(signal_returns, dtype=float)
    baseline = np.asarray(baseline_returns, dtype=float)

    def stats(values: np.ndarray) -> dict:
        if values.size == 0:
            return {"n": 0, "trefferquote": None, "median": None, "mittel": None,
                    "q25": None, "q75": None, "bestes": None, "schlechtestes": None}
        return {
            "n": int(values.size),
            "trefferquote": round(float((values > 0).mean() * 100), 1),
            "median": round(float(np.median(values)), 2),
            "mittel": round(float(values.mean()), 2),
            "q25": round(float(np.percentile(values, 25)), 2),
            "q75": round(float(np.percentile(values, 75)), 2),
            "bestes": round(float(values.max()), 2),
            "schlechtestes": round(float(values.min()), 2),
        }

    signal_stats = stats(signals)
    baseline_stats = stats(baseline)

    edge_hit = edge_median = None
    if signal_stats["n"] and baseline_stats["n"]:
        edge_hit = round(signal_stats["trefferquote"] - baseline_stats["trefferquote"], 1)
        edge_median = round(signal_stats["median"] - baseline_stats["median"], 2)

    return {
        "signal": signal_stats,
        "vergleich": baseline_stats,
        "vorsprung_trefferquote_pp": edge_hit,
        "vorsprung_median_pp": edge_median,
        "belastbar": bool(signal_stats["n"] >= MIN_SIGNALS_FOR_STATS),
    }


def evaluate_strategy(
    strategy: Strategy,
    frames: dict[str, pd.DataFrame],
    benchmark: pd.Series | None = None,
    names: dict[str, str] | None = None,
) -> dict:
    """Auswertung ueber mehrere Titel. ``frames`` bildet ISIN auf Kursreihe ab."""
    names = names or {}
    all_signals: list[float] = []
    all_baseline: list[float] = []
    per_instrument: list[dict] = []
    first_date: pd.Timestamp | None = None
    last_date: pd.Timestamp | None = None

    for isin, frame in frames.items():
        if frame.empty:
            continue
        first_date = frame.index[0] if first_date is None else min(first_date, frame.index[0])
        last_date = frame.index[-1] if last_date is None else max(last_date, frame.index[-1])

        try:
            signals, baseline = evaluate_instrument(strategy, frame, benchmark)
        except Exception as exc:
            log.warning("Auswertung %s fehlgeschlagen: %s", isin, exc)
            continue

        all_signals.extend(signals)
        all_baseline.extend(baseline)
        if signals:
            values = np.asarray(signals)
            per_instrument.append(
                {
                    "isin": isin,
                    "name": names.get(isin, isin),
                    "n": len(signals),
                    "trefferquote": round(float((values > 0).mean() * 100), 1),
                    "median": round(float(np.median(values)), 2),
                }
            )

    payload = summarise(all_signals, all_baseline)
    payload.update(
        {
            "strategie": strategy.name,
            "label": strategy.label,
            "haltedauer_tage": strategy.risk.max_holding_days,
            "titel_ausgewertet": len(frames),
            "titel_mit_signal": len(per_instrument),
            "zeitraum_von": first_date.date().isoformat() if first_date is not None else None,
            "zeitraum_bis": last_date.date().isoformat() if last_date is not None else None,
            "je_titel": sorted(per_instrument, key=lambda d: -d["n"])[:25],
            "hinweise": [
                "Einstieg zur Eroeffnung des Folgetages, Ausstieg zum Schluss nach "
                f"{strategy.risk.max_holding_days} Handelstagen.",
                "Nur ein Signal je Haltedauer und Titel, damit derselbe Kursverlauf "
                "nicht mehrfach gezaehlt wird.",
                "Ohne Gebuehren, Spread und Steuern.",
                "Delistete Titel fehlen in der Datenquelle - die Ergebnisse sind "
                "dadurch systematisch zu optimistisch.",
                "Keine Aussage ueber die Zukunft. Mit genuegend Parametervarianten "
                "sieht jede Regel irgendwann gut aus.",
            ],
        }
    )
    return payload
