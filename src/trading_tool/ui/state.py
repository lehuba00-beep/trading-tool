"""Gemeinsamer Zustand der Anwendung.

Buendelt Datenbank, Cache, Strategien und Hintergrundlaeufe an einer Stelle,
damit die Routen keine eigenen Verbindungen aufmachen.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..backtest import evaluate_strategy
from ..config import Settings, bundle_dir
from ..derivatives import load_issuers
from ..providers.registry import ProviderChain
from ..screener.engine import Screener
from ..storage.cache import PriceCache
from ..storage.db import init_db
from ..storage.repositories import (
    BacktestRepo,
    InstrumentRepo,
    RunRepo,
    SignalRepo,
    WatchlistRepo,
)
from ..strategies import load_all
from ..universe import load as load_universe
from .jobs import JobRunner
from .scheduler import ScreeningScheduler

log = logging.getLogger(__name__)


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.conn = init_db(settings.db_path)
        self.chain = ProviderChain(settings)
        self.cache = PriceCache(self.conn, self.chain, settings)
        self.strategies = load_all(settings.strategy_dir)
        self.screener = Screener(self.conn, self.cache, settings, self.strategies)
        self.instruments = InstrumentRepo(self.conn)
        self.watchlist = WatchlistRepo(self.conn)
        self.runs = RunRepo(self.conn)
        self.signals = SignalRepo(self.conn)
        self.backtests = BacktestRepo(self.conn)
        self.jobs = JobRunner()
        self.issuers = load_issuers(bundle_dir() / "config" / "issuers.yaml")
        self.universe_report = None
        self.scheduler = ScreeningScheduler(settings, self.run_all_strategies)

    # ------------------------------------------------------------- Aufbau

    def import_universe(self) -> None:
        """Universumsliste einlesen. Ohne sie gibt es nichts zu screenen."""
        path = self.settings.universe_path
        instruments, report = load_universe(path)
        self.universe_report = report
        if report.errors:
            log.error("Universumsliste %s: %s", path, report.summary())
            for message in report.errors[:10]:
                log.error("  %s", message)
        if instruments:
            self.instruments.upsert_many(instruments)
            log.info("Universum geladen: %d Instrumente aus %s", len(instruments), path)

    def active_strategies(self) -> dict:
        configured = self.settings.screening.strategies
        ordered = {n: self.strategies[n] for n in configured if n in self.strategies}
        # Profile, die in den Einstellungen fehlen, aber als Datei vorliegen,
        # sollen trotzdem erreichbar sein.
        for name, strategy in self.strategies.items():
            ordered.setdefault(name, strategy)
        return ordered

    # -------------------------------------------------------------- Laeufe

    def submit_screening(self, name: str, only_watchlist: bool = False) -> bool:
        strategy = self.strategies.get(name)
        if strategy is None:
            return False

        def task(progress):
            run_id, signals = self.screener.run(name, only_watchlist, True, progress)
            return {"run_id": run_id, "treffer": len(signals)}

        return self.jobs.submit(f"screening:{name}", f"Screening {strategy.label}", task)

    def run_all_strategies(self, label: str = "") -> None:
        for name in self.active_strategies():
            self.submit_screening(name)

    def submit_backtest(self, name: str) -> bool:
        strategy = self.strategies.get(name)
        if strategy is None:
            return False

        def task(progress):
            instruments = self.screener.candidates(strategy)
            benchmark = self.screener._benchmark_series(strategy)
            frames: dict[str, object] = {}
            names: dict[str, str] = {}
            for number, instrument in enumerate(instruments, start=1):
                progress(number, len(instruments), f"Historie {instrument.name}")
                frame = self.cache.bars_in_base_currency(instrument)
                if not frame.empty:
                    frames[instrument.isin] = frame
                    names[instrument.isin] = instrument.name
            progress(len(instruments), len(instruments), "Auswertung")
            payload = evaluate_strategy(strategy, frames, benchmark, names)
            self.backtests.save(name, payload)
            return {"signale": payload["signal"]["n"]}

        return self.jobs.submit(f"backtest:{name}", f"Trefferquote {strategy.label}", task)

    def close(self) -> None:
        # Reihenfolge zaehlt: erst keine neuen Auftraege mehr zulassen, dann
        # den laufenden abwarten, erst danach die Datenbank schliessen. Sonst
        # zieht man einem laufenden Screening die Verbindung unter den Fuessen weg.
        self.scheduler.shutdown()
        self.jobs.stop()
        self.conn.close()


def _resource(name: str) -> Path:
    """Mitgelieferte Dateien finden - im Repository wie im PyInstaller-Bundle."""
    local = Path(__file__).resolve().parent / name
    if local.is_dir():
        return local
    return bundle_dir() / "trading_tool" / "ui" / name


def templates_dir() -> Path:
    return _resource("templates")


def static_dir() -> Path:
    return _resource("static")
