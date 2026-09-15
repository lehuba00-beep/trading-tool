"""Einstiegspunkt.

Ohne Argumente startet die Weboberflaeche und oeffnet den Browser. Die
Unterbefehle sind fuer den Betrieb ohne Oberflaeche gedacht - und dafuer, dass
sich beim Einrichten pruefen laesst, ob Daten und Regeln stimmen, bevor eine
Oberflaeche dazwischensteht.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from .config import load_settings


def _setup_logging(verbose: bool = False) -> None:
    settings = load_settings()
    log_path = settings.data_dir / "trading-tool.log"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    # Kein Schreibrecht im Datenverzeichnis: dann eben nur Konsole.
    with contextlib.suppress(OSError):
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    # yfinance meldet jeden fehlgeschlagenen Einzelabruf - im Lauf ueber
    # hunderte Titel ist das nur Rauschen.
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _free_port(preferred: int = 0) -> int:
    """Freien Port suchen. Ein fest verdrahteter Port kollidiert irgendwann."""
    if preferred:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", preferred)) != 0:
                return preferred
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def command_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .ui.app import create_app

    settings = load_settings()
    port = _free_port(args.port or settings.ui.port)
    url = f"http://{settings.ui.host}:{port}"

    app = create_app(settings)
    if settings.ui.open_browser and not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    print(f"\n  Trading-Tool laeuft auf {url}")
    print("  Beenden mit Strg+C\n")
    uvicorn.run(app, host=settings.ui.host, port=port, log_level="warning")
    return 0


def _build_state():
    from .ui.state import AppState

    settings = load_settings()
    state = AppState(settings)
    state.import_universe()
    return state


def command_screen(args: argparse.Namespace) -> int:
    state = _build_state()
    names = [args.strategy] if args.strategy else list(state.active_strategies())

    for name in names:
        if name not in state.strategies:
            print(f"Unbekannte Strategie '{name}'. "
                  f"Verfuegbar: {', '.join(state.strategies)}")
            return 2

        def progress(current: int, total: int, message: str) -> None:
            print(f"\r  [{current:>4}/{total}] {message[:58]:<58}", end="", flush=True)

        print(f"\n{state.strategies[name].label}")
        _, signals = state.screener.run(name, args.watchlist, not args.no_refresh, progress)
        print("\r" + " " * 72 + "\r", end="")

        if not signals:
            print("  keine Treffer")
        for signal in signals[: args.limit]:
            flag = " (vorlaeufig)" if signal.provisional else ""
            print(f"  {signal.score:5.1f}  {signal.name[:34]:<34} "
                  f"{signal.metrics.get('kurs_eur', 0):>9,.2f} EUR{flag}")
            print(f"         {', '.join(signal.triggered_labels[:4])}")

        if args.export:
            from .reporting import to_csv
            path = to_csv(signals, state.settings.export_dir, name)
            print(f"  -> {path}")

    state.close()
    return 0


def command_backtest(args: argparse.Namespace) -> int:
    from .backtest import evaluate_strategy

    state = _build_state()
    name = args.strategy
    strategy = state.strategies.get(name)
    if strategy is None:
        print(f"Unbekannte Strategie '{name}'")
        return 2

    instruments = state.screener.candidates(strategy)
    benchmark = state.screener._benchmark_series(strategy)
    frames, names = {}, {}
    for instrument in instruments:
        frame = state.cache.bars_in_base_currency(instrument)
        if not frame.empty:
            frames[instrument.isin] = frame
            names[instrument.isin] = instrument.name

    if not frames:
        print("Keine Kurshistorie im Cache. Zuerst 'screen' laufen lassen.")
        return 1

    result = evaluate_strategy(strategy, frames, benchmark, names)
    state.backtests.save(name, result)
    signal, baseline = result["signal"], result["vergleich"]

    print(f"\n{strategy.label} - Haltedauer {result['haltedauer_tage']} Handelstage")
    print(f"  Zeitraum {result['zeitraum_von']} bis {result['zeitraum_bis']}, "
          f"{result['titel_ausgewertet']} Titel")
    print(f"  Signal      n={signal['n']:>6}  Trefferquote {signal['trefferquote']}%  "
          f"Median {signal['median']}%")
    print(f"  Vergleich   n={baseline['n']:>6}  Trefferquote {baseline['trefferquote']}%  "
          f"Median {baseline['median']}%")
    print(f"  Vorsprung   {result['vorsprung_trefferquote_pp']} Pp Trefferquote, "
          f"{result['vorsprung_median_pp']} Pp Median")
    if not result["belastbar"]:
        print("  ACHTUNG: zu wenige Beobachtungen - die Zahlen sind nicht belastbar.")
    state.close()
    return 0


def command_universe(args: argparse.Namespace) -> int:
    from .universe import load

    settings = load_settings()
    path = Path(args.path) if args.path else settings.universe_path
    instruments, report = load(path)

    print(f"\n{path}")
    print(f"  {report.summary()}")
    for message in report.errors[:25]:
        print(f"  FEHLER   {message}")
    for message in report.warnings[:25]:
        print(f"  HINWEIS  {message}")
    print(f"  {len(instruments)} Instrumente verwendbar")
    return 0 if report.ok else 1


def command_rules(_: argparse.Namespace) -> int:
    import inspect

    from .strategies.rules import REGISTRY

    print(f"\n{len(REGISTRY)} Regelbausteine:\n")
    for name in sorted(REGISTRY):
        signature = inspect.signature(REGISTRY[name])
        params = [
            f"{p.name}={p.default!r}"
            for p in signature.parameters.values()
            if p.name != "ctx"
        ]
        print(f"  {name}")
        print(f"      {', '.join(params) or '(ohne Parameter)'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trading-tool",
        description="Analyse- und Screening-Werkzeug. Keine Anlageberatung, "
                    "keine Broker-Anbindung, keine Orderausfuehrung.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Weboberflaeche starten (Vorgabe)")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--no-browser", action="store_true")
    serve.set_defaults(func=command_serve)

    screen = sub.add_parser("screen", help="Screening ohne Oberflaeche")
    screen.add_argument("--strategy", "-s", default="")
    screen.add_argument("--watchlist", action="store_true", help="nur Watchlist")
    screen.add_argument("--no-refresh", action="store_true", help="keine Kurse nachladen")
    screen.add_argument("--limit", type=int, default=15)
    screen.add_argument("--export", action="store_true", help="CSV schreiben")
    screen.set_defaults(func=command_screen)

    backtest = sub.add_parser("backtest", help="Trefferquote historischer Signale")
    backtest.add_argument("--strategy", "-s", required=True)
    backtest.set_defaults(func=command_backtest)

    universe = sub.add_parser("universe", help="Universumsliste pruefen")
    universe.add_argument("--path", default="")
    universe.set_defaults(func=command_universe)

    rules = sub.add_parser("rules", help="Verfuegbare Regelbausteine auflisten")
    rules.set_defaults(func=command_rules)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if not getattr(args, "func", None):
        args = parser.parse_args(["serve", *(argv or [])])
        _setup_logging(args.verbose)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
