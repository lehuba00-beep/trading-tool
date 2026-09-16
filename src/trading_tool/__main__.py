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

from .config import DEFAULT_LAN_PORT, load_settings


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


def _free_port(preferred: int = 0) -> tuple[int, bool]:
    """(Port, ob ausgewichen wurde).

    Ob ausgewichen wurde, ist beim Zugriff vom Handy wichtig: Dann stimmt das
    Lesezeichen nicht mehr, und das muss sichtbar sein statt still zu
    passieren.
    """
    if preferred:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", preferred)) != 0:
                return preferred, False
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1]), bool(preferred)


def _lan_address() -> str:
    """Eigene Adresse im Heimnetz ermitteln.

    Der Umweg ueber eine Verbindung nach aussen ist der zuverlaessigste Weg,
    die richtige Schnittstelle zu finden - es werden dabei keine Daten
    gesendet, das Betriebssystem waehlt nur die Route.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # Adresse aus dem Dokumentationsbereich
        return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def command_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .ui.app import create_app
    from .ui.auth import bind_host, lan_ready, tls_active

    settings = load_settings()
    bereit, meldung = lan_ready(settings)
    if not bereit:
        print(f"\n  {meldung}\n")
        return 2

    gewuenscht = args.port or settings.ui.preferred_port()
    port, ausgewichen = _free_port(gewuenscht)
    host = bind_host(settings)

    ssl_argumente = {}
    schema = "http"
    if tls_active(settings):
        from .tls import ensure_certificate

        zertifikat = ensure_certificate(settings.data_dir)
        ssl_argumente = {
            "ssl_certfile": str(zertifikat.server_cert),
            "ssl_keyfile": str(zertifikat.server_key),
        }
        schema = "https"

    url = f"{schema}://127.0.0.1:{port}"
    app = create_app(settings)
    if settings.ui.open_browser and not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    print(f"\n  Trading-Tool laeuft auf {url}")
    if ausgewichen:
        print(f"  Hinweis: Port {gewuenscht} ist belegt, daher {port}.")
        if settings.ui.allow_lan:
            print("  Ein Lesezeichen auf dem Handy zeigt damit ins Leere -")
            print("  entweder das belegende Programm beenden oder in")
            print("  settings.yaml unter ui.port einen anderen Port eintragen.")
    if settings.ui.allow_lan:
        adresse = f"{schema}://{_lan_address()}:{port}"
        print(f"  Im Heimnetz erreichbar: {adresse}")
        if schema == "https":
            print("  Verschluesselt und passwortgeschuetzt.")
            print(f"  Zertifikat fuers Handy: {adresse}/ca.crt  (einmalig hinterlegen)")
        else:
            print("  ACHTUNG: unverschluesselt - Passwort und Daten gehen offen durchs Netz.")
        print("  Fuer den Zugriff von unterwegs ein VPN nutzen, keine Portfreigabe:")
        print("  Verschluesselung schuetzt den Weg, nicht die Erreichbarkeit.")
    print("  Beenden mit Strg+C\n")
    uvicorn.run(app, host=host, port=port, log_level="warning", **ssl_argumente)
    return 0


def command_certificate(args: argparse.Namespace) -> int:
    """Zertifikat neu ausstellen und den Weg aufs Handy zeigen."""
    from .tls import ensure_certificate, local_addresses, paths

    settings = load_settings()
    zertifikat = ensure_certificate(settings.data_dir, force=args.neu)
    namen, adressen = local_addresses()

    print("\n  Zertifikat bereit.")
    print(f"  Gueltig fuer: {', '.join(namen)} / {', '.join(adressen)}")
    print(f"  Stelle:  {paths(settings.data_dir).ca_cert}")
    print(f"  Server:  {zertifikat.server_cert}")
    print("\n  Auf dem Handy einmalig hinterlegen:")
    print(f"    1. https://{_lan_address()}:<Port>/ca.crt im Browser oeffnen")
    print("    2. Datei oeffnen und als Zertifizierungsstelle installieren")
    print("       (Android: Einstellungen > Sicherheit > Verschluesselung >")
    print("        Zertifikat installieren > CA-Zertifikat)")
    print("\n  Ohne diesen Schritt zeigt der Browser eine Warnung, die sich")
    print("  einmalig bestaetigen laesst - verschluesselt ist die Verbindung so")
    print("  oder so.\n")
    return 0


def command_password(args: argparse.Namespace) -> int:
    """Passwort fuer den Zugriff aus dem Netz setzen oder entfernen."""
    import getpass

    from .config import save_settings
    from .ui.auth import hash_password

    settings = load_settings()

    if args.entfernen:
        settings.ui.password_hash = ""
        settings.ui.allow_lan = False
        save_settings(settings)
        print("\n  Passwort entfernt. Der Zugriff aus dem Netz ist wieder aus.\n")
        return 0

    erstes = getpass.getpass("  Neues Passwort: ")
    if len(erstes) < 8:
        print("\n  Zu kurz - mindestens acht Zeichen.\n")
        return 2
    if erstes != getpass.getpass("  Wiederholen:    "):
        print("\n  Die Eingaben stimmen nicht ueberein.\n")
        return 2

    settings.ui.password_hash = hash_password(erstes)
    fester_port = 0
    if args.netz:
        settings.ui.allow_lan = True
        if not settings.ui.port:
            # Ausdruecklich in die Einstellungen schreiben statt nur als
            # Vorgabe zu verwenden: So steht die Adresse sichtbar in der
            # Datei und laesst sich dort aendern.
            settings.ui.port = DEFAULT_LAN_PORT
            fester_port = DEFAULT_LAN_PORT
    save_settings(settings)

    print("\n  Passwort gesetzt.")
    if settings.ui.allow_lan:
        adresse = f"https://{_lan_address()}:{settings.ui.port}"
        print(f"  Zugriff aus dem Heimnetz ist eingeschaltet: {adresse}")
        if fester_port:
            print(f"  Fester Port {fester_port} eingetragen - die Adresse bleibt damit")
            print("  ueber Neustarts gleich und laesst sich als Lesezeichen speichern.")
        print("\n  Naechster Schritt:  TradingTool.exe zertifikat")
    else:
        print("  Zugriff aus dem Netz ist weiterhin aus.")
        print("  Einschalten mit:  TradingTool.exe passwort --netz")
    print()
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

    # Zeilenweises Ueberschreiben nur im Terminal - in eine Datei oder Pipe
    # umgeleitet erzeugt das sonst eine einzige unlesbare Zeile.
    interaktiv = sys.stdout.isatty()

    def progress(current: int, total: int, message: str) -> None:
        if interaktiv:
            print(f"\r  [{current:>4}/{total}] {message[:58]:<58}", end="", flush=True)

    for name in names:
        if name not in state.strategies:
            print(f"Unbekannte Strategie '{name}'. "
                  f"Verfuegbar: {', '.join(state.strategies)}")
            return 2

        print(f"\n{state.strategies[name].label}")
        _, signals = state.screener.run(name, args.watchlist, not args.no_refresh, progress)
        if interaktiv:
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

    passwort = sub.add_parser(
        "passwort", help="Passwort fuer den Zugriff aus dem Heimnetz setzen"
    )
    passwort.add_argument("--netz", action="store_true",
                          help="Zugriff aus dem Heimnetz zugleich einschalten")
    passwort.add_argument("--entfernen", action="store_true",
                          help="Passwort loeschen und Netzzugriff abschalten")
    passwort.set_defaults(func=command_password)

    zertifikat = sub.add_parser(
        "zertifikat", help="Verschluesselung einrichten oder Zertifikat erneuern"
    )
    zertifikat.add_argument("--neu", action="store_true",
                            help="Serverzertifikat neu ausstellen")
    zertifikat.set_defaults(func=command_certificate)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if not getattr(args, "func", None):
        args = parser.parse_args(["serve", *(argv or [])])
        _setup_logging(args.verbose)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
