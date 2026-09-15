"""Screening-Engine.

Ein Lauf wertet genau eine Strategie ueber das gefilterte Universum aus. Die
Reihenfolge ist bewusst: erst alle Kursdaten aktualisieren, dann rechnen. So
haengt das Ergebnis nicht davon ab, wie lange der Abruf gedauert hat.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import date

import pandas as pd

from ..config import Settings
from ..domain.models import Instrument, Signal
from ..storage.cache import PriceCache
from ..storage.repositories import InstrumentRepo, RunRepo, SignalRepo, WatchlistRepo
from ..strategies.base import Strategy, StrategyEvaluation
from ..strategies.context import IndicatorContext

log = logging.getLogger(__name__)

Progress = Callable[[int, int, str], None]


class Screener:
    def __init__(
        self,
        conn: sqlite3.Connection,
        cache: PriceCache,
        settings: Settings,
        strategies: dict[str, Strategy],
    ) -> None:
        self.conn = conn
        self.cache = cache
        self.settings = settings
        self.strategies = strategies
        self.instruments = InstrumentRepo(conn)
        self.watchlist = WatchlistRepo(conn)
        self.runs = RunRepo(conn)
        self.signals = SignalRepo(conn)

    # ------------------------------------------------------------------ API

    def candidates(self, strategy: Strategy, only_watchlist: bool = False) -> list[Instrument]:
        allowed = [s for s in strategy.universe.tr_status
                   if s in self.settings.screening.include_tr_status]
        instruments = self.instruments.screenable(allowed, strategy.universe.asset_class)
        if only_watchlist:
            watched = set(self.watchlist.isins())
            instruments = [i for i in instruments if i.isin in watched]
        return instruments

    def refresh_prices(
        self, instruments: list[Instrument], strategy: Strategy, progress: Progress | None = None
    ) -> None:
        """Kurse, Devisen und Vergleichsreihe aktualisieren."""
        currencies = {i.currency for i in instruments}
        self.cache.refresh_fx(currencies)

        targets = list(instruments)
        benchmark = self._benchmark_instrument(strategy)
        if benchmark is not None and benchmark.isin not in {i.isin for i in instruments}:
            targets.append(benchmark)

        for number, instrument in enumerate(targets, start=1):
            if progress:
                progress(number, len(targets), f"Kurse {instrument.name}")
            try:
                self.cache.refresh(instrument)
            except Exception as exc:  # ein kaputtes Symbol darf den Lauf nicht kippen
                log.warning("Kursabruf %s fehlgeschlagen: %s", instrument.isin, exc)

    def run(
        self,
        strategy_name: str,
        only_watchlist: bool = False,
        refresh: bool = True,
        progress: Progress | None = None,
    ) -> tuple[int, list[Signal]]:
        strategy = self.strategies.get(strategy_name)
        if strategy is None:
            raise KeyError(f"Unbekannte Strategie '{strategy_name}'")

        instruments = self.candidates(strategy, only_watchlist)
        run_id = self.runs.start(strategy_name, self.cache.chain.primary_name)

        try:
            if refresh:
                self.refresh_prices(instruments, strategy, progress)

            benchmark = self._benchmark_series(strategy)
            results: list[Signal] = []
            skipped_history = 0
            skipped_liquidity = 0

            for number, instrument in enumerate(instruments, start=1):
                if progress:
                    progress(number, len(instruments), f"Analyse {instrument.name}")

                frame = self.cache.bars_in_base_currency(instrument)
                if len(frame) < strategy.universe.min_history_days:
                    skipped_history += 1
                    continue

                ctx = IndicatorContext(frame, benchmark)

                if strategy.universe.min_avg_turnover_eur > 0:
                    recent_turnover = ctx.turnover(20).iloc[-1]
                    if pd.isna(recent_turnover) or (
                        recent_turnover < strategy.universe.min_avg_turnover_eur
                    ):
                        skipped_liquidity += 1
                        continue

                evaluation = strategy.evaluate(ctx)
                if not bool(evaluation.eligible.iloc[-1]):
                    continue
                results.append(self._build_signal(instrument, strategy, ctx, evaluation))

            results.sort(key=lambda s: s.score, reverse=True)
            self.signals.save_many(run_id, results)
            self.runs.finish(
                run_id, len(instruments), len(results), "ok",
                f"uebersprungen: {skipped_history} ohne Historie, "
                f"{skipped_liquidity} zu illiquide",
            )
            return run_id, results

        except Exception as exc:
            self.runs.finish(run_id, len(instruments), 0, "error", str(exc))
            raise

    # -------------------------------------------------------------- intern

    def _benchmark_instrument(self, strategy: Strategy) -> Instrument | None:
        if not strategy.benchmark:
            return None
        instrument = self.instruments.get(strategy.benchmark)
        if instrument is None:
            log.warning(
                "Vergleichsreihe '%s' nicht im Universum - Regeln zur relativen "
                "Staerke koennen nicht erfuellt werden", strategy.benchmark,
            )
        return instrument

    def _benchmark_series(self, strategy: Strategy) -> pd.Series | None:
        instrument = self._benchmark_instrument(strategy)
        if instrument is None:
            return None
        # Auch die Vergleichsreihe wird nach EUR umgerechnet - sonst misst die
        # Ueberrendite zum Teil nur die Wechselkursbewegung.
        frame = self.cache.bars_in_base_currency(instrument)
        return frame["adj_close"] if not frame.empty else None

    def _build_signal(
        self,
        instrument: Instrument,
        strategy: Strategy,
        ctx: IndicatorContext,
        evaluation: StrategyEvaluation,
    ) -> Signal:
        last = ctx.index[-1].date()
        close = float(ctx.close.iloc[-1])
        atr_value = float(ctx.atr(strategy.risk.atr_period).iloc[-1])

        metrics = {
            "kurs_eur": round(close, 4),
            "atr": round(atr_value, 4),
            "atr_pct": _round(ctx.atr_pct(strategy.risk.atr_period).iloc[-1]),
            "stop": round(close - strategy.risk.stop_atr_factor * atr_value, 4),
            "ziel": round(close + strategy.risk.target_atr_factor * atr_value, 4),
            "stop_abstand_pct": _round(strategy.risk.stop_atr_factor * atr_value / close * 100),
            "rsi_14": _round(ctx.rsi(14).iloc[-1]),
            "adx_14": _round(ctx.adx(14).iloc[-1]),
            "rel_volumen": _round(ctx.relative_volume(20).iloc[-1]),
            "umsatz_20d_eur": _round(ctx.turnover(20).iloc[-1], 0),
            "abstand_52w_hoch_pct": _round(ctx.distance_to_high(252).iloc[-1]),
            "perf_20d_pct": _round(ctx.roc(20).iloc[-1]),
            "perf_126d_pct": _round(ctx.roc(126).iloc[-1]),
            "vola_ann_pct": _round(ctx.realized_vol(60).iloc[-1]),
        }
        rs = ctx.relative_strength(126)
        if rs is not None:
            metrics["ueberrendite_126d_pp"] = _round(rs.iloc[-1])

        return Signal(
            isin=instrument.isin,
            name=instrument.name,
            strategy=strategy.name,
            horizon=strategy.horizon,
            direction=strategy.direction,
            score=round(float(evaluation.score.iloc[-1]), 1),
            as_of=last,
            hits=evaluation.hits_at(-1),
            metrics=metrics,
            tr_status=instrument.tr_status,
            # Der Tagesbalken des laufenden Handelstages ist noch nicht
            # abgeschlossen. Ein darauf beruhendes Signal kann sich bis
            # Handelsschluss wieder aufloesen - das muss sichtbar bleiben.
            provisional=last >= date.today(),
        )


def _round(value, digits: int = 2) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)
