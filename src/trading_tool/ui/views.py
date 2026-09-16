"""Routen der Weboberflaeche."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from ..derivatives import GENERAL_RISKS, leverage_hint, products_for, tr_search_hint
from ..domain.enums import Direction, TRStatus
from ..quality import Severity, check_series
from ..reporting import to_csv, to_xlsx
from ..screener.ranking import sort_signals
from ..strategies.context import IndicatorContext
from .auth import COOKIE_NAME, SESSION_MAX_AGE, issue_token, verify_password

log = logging.getLogger(__name__)
router = APIRouter()


def _state(request: Request):
    return request.app.state.app


def _templates(request: Request):
    return request.app.state.templates


def _render(request: Request, template: str, **context) -> HTMLResponse:
    state = _state(request)
    context.setdefault("strategies", state.active_strategies())
    context.setdefault("job", state.jobs.state)
    context.setdefault("kurs_status", state.quotes.status())
    context.setdefault("geschuetzt", bool(state.settings.ui.password_hash))
    context.setdefault("request", request)
    return _templates(request).TemplateResponse(request, template, context)


# ------------------------------------------------------------------ Start

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    state = _state(request)
    cards = []
    for name, strategy in state.active_strategies().items():
        run = state.runs.latest(name)
        cards.append(
            {
                "name": name,
                "strategy": strategy,
                "run": run,
                "signals": state.signals.for_run(run.id, 0) if run and run.id else [],
            }
        )

    stale = state.instruments.stale_checks(state.settings.screening.tr_check_stale_days)
    coverage = state.cache.bars.coverage()
    return _render(
        request, "index.html",
        cards=cards, stale=stale[:20], stale_total=len(stale), coverage=coverage,
        next_runs=state.scheduler.next_runs(), report=state.universe_report,
    )


# --------------------------------------------------------------- Screening

@router.get("/screener/{name}", response_class=HTMLResponse)
def screener(request: Request, name: str, sort: str = "score", nur_geprueft: int = 0):
    state = _state(request)
    strategy = state.strategies.get(name)
    if strategy is None:
        return RedirectResponse("/", status_code=303)

    run = state.runs.latest(name)
    signals = state.signals.for_run(run.id, 0) if run and run.id else []
    if nur_geprueft:
        signals = [s for s in signals if s.tr_status is TRStatus.VERIFIED]
    signals = sort_signals(signals, sort)
    watched = set(state.watchlist.isins())

    return _render(
        request, "screener.html",
        name=name, strategy=strategy, run=run, signals=signals,
        sort=sort, nur_geprueft=nur_geprueft, watched=watched,
    )


@router.post("/screener/{name}/run")
def run_screener(request: Request, name: str, nur_watchlist: str = Form(default="")):
    state = _state(request)
    state.submit_screening(name, only_watchlist=bool(nur_watchlist))
    return RedirectResponse(f"/screener/{name}", status_code=303)


@router.post("/screener/alle/run")
def run_all(request: Request):
    _state(request).run_all_strategies("manuell")
    return RedirectResponse("/", status_code=303)


@router.get("/jobs/status", response_class=HTMLResponse)
def job_status(request: Request):
    """HTMX-Fragment: Fortschrittsanzeige, alle zwei Sekunden abgefragt."""
    state = _state(request)
    return _render(request, "_job.html", job=state.jobs.state, pending=state.jobs.pending)


# ------------------------------------------------------------------ PWA

@router.get("/manifest.webmanifest", include_in_schema=False)
def manifest(request: Request):
    from .state import static_dir

    return FileResponse(static_dir() / "manifest.webmanifest",
                        media_type="application/manifest+json")


@router.get("/sw.js", include_in_schema=False)
def service_worker(request: Request):
    """Muss von der Wurzel ausgeliefert werden.

    Ein Service Worker darf nur den Pfad steuern, unter dem er selbst liegt -
    unter /static/ koennte er die Anwendung nicht bedienen.
    """
    from .state import static_dir

    return FileResponse(
        static_dir() / "sw.js", media_type="text/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@router.get("/icons/{name}", include_in_schema=False)
def icon(request: Request, name: str):
    from .state import static_dir

    pfad = (static_dir() / "icons" / name).resolve()
    erlaubt = (static_dir() / "icons").resolve()
    # Pfad einsperren: Ohne diese Pruefung liesse sich ueber ../ jede Datei
    # des Rechners abrufen.
    if not str(pfad).startswith(str(erlaubt)) or not pfad.is_file():
        return RedirectResponse("/static/icons/icon-192.png", status_code=303)
    return FileResponse(pfad, media_type="image/png")


@router.get("/ca.crt", include_in_schema=False)
def zertifizierungsstelle(request: Request):
    """Die eigene Zertifizierungsstelle zum Hinterlegen auf dem Handy.

    Einmal installiert, gilt sie auch fuer spaeter neu ausgestellte
    Serverzertifikate - etwa nach einem Adresswechsel aus dem Router.
    """
    from ..tls import paths

    state = _state(request)
    datei = paths(state.settings.data_dir).ca_cert
    if not datei.exists():
        return RedirectResponse("/einstellungen", status_code=303)
    return FileResponse(
        datei, media_type="application/x-x509-ca-cert", filename="trading-tool-ca.crt"
    )


# ------------------------------------------------------------------ Anmeldung

@router.get("/anmelden", response_class=HTMLResponse)
def anmelden_formular(request: Request, weiter: str = "/", fehler: int = 0):
    state = _state(request)
    if not state.settings.ui.password_hash:
        return RedirectResponse("/", status_code=303)
    return _templates(request).TemplateResponse(
        request, "login.html",
        {"request": request, "weiter": weiter, "fehler": bool(fehler),
         "strategies": {}, "kurs_status": {"aktiv": False, "intervall": 0}},
    )


@router.post("/anmelden")
async def anmelden(request: Request, passwort: str = Form(...), weiter: str = Form(default="/")):
    import asyncio

    state = _state(request)
    bremse = request.app.state.throttle

    if not verify_password(passwort, state.settings.ui.password_hash):
        # Verzoegerung nach Fehlversuch: macht systematisches Durchprobieren
        # unbrauchbar, ohne den Nutzer auszusperren.
        await asyncio.sleep(bremse.failed())
        ziel = f"/anmelden?fehler=1&weiter={quote(weiter, safe='')}"
        return RedirectResponse(ziel, status_code=303)

    bremse.succeeded()
    # Nur eigene Pfade als Ziel zulassen - sonst liesse sich die Anmeldung
    # nutzen, um auf eine fremde Adresse weiterzuleiten.
    ziel = weiter if weiter.startswith("/") and not weiter.startswith("//") else "/"
    antwort = RedirectResponse(ziel, status_code=303)
    antwort.set_cookie(
        COOKIE_NAME, issue_token(request.app.state.secret),
        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
        # Ueber HTTPS nur verschluesselt senden. Auf HTTP waere das Merkmal
        # kontraproduktiv - der Browser wuerde das Plaetzchen nie schicken.
        secure=request.url.scheme == "https",
    )
    return antwort


@router.post("/abmelden")
def abmelden(request: Request):
    antwort = RedirectResponse("/anmelden", status_code=303)
    antwort.delete_cookie(COOKIE_NAME)
    return antwort


# ------------------------------------------------------------------ Kurse

@router.get("/kurse")
def kurse(request: Request, isins: str = ""):
    """Laufend aktualisierte Kurse als JSON.

    Ausdruecklich keine Echtzeitkurse - Yahoo liefert je nach Boerse 15 bis 20
    Minuten verzoegert. Der Abrufzeitpunkt wird mitgeliefert und in der
    Oberflaeche angezeigt, damit niemand die Verzoegerung uebersieht.
    """
    state = _state(request)
    gewuenscht = [i.strip() for i in isins.split(",") if i.strip()]
    if not gewuenscht:
        return JSONResponse({"kurse": {}, **state.quotes.status()})

    instrumente = [
        instrument
        for instrument in (state.instruments.get(isin) for isin in gewuenscht)
        if instrument is not None
    ]
    quotes = state.quotes.get(instrumente)

    return JSONResponse(
        {
            "kurse": {
                isin: {
                    "preis": round(q.price, 4),
                    "veraenderung": round(q.change_pct, 2) if q.change_pct is not None else None,
                }
                for isin, q in quotes.items()
            },
            **state.quotes.status(),
        }
    )


# ------------------------------------------------------------ Datenqualitaet

@router.get("/datenqualitaet", response_class=HTMLResponse)
def datenqualitaet(request: Request, nur_probleme: int = 1):
    """Kursreihen auf Auffaelligkeiten pruefen.

    Ein fehlerhafter Einzelkurs erzeugt ein makelloses Ausbruchssignal, und
    eine stehengebliebene Reihe laesst alle Indikatoren weiterrechnen - nur
    eben auf altem Stand. Beides ist ohne Pruefung nicht zu sehen.
    """
    state = _state(request)
    instrumente = state.instruments.screenable(
        ["verified", "assumed"], ["stock", "etf"]
    )

    berichte = []
    for instrument in instrumente:
        frame = state.cache.bars_in_base_currency(instrument)
        bericht = check_series(frame, instrument.isin)
        if nur_probleme and bericht.ok:
            continue
        berichte.append((instrument, bericht))

    berichte.sort(key=lambda paar: (-paar[1].severity.rank, paar[0].name))
    zaehler = {
        "gesamt": len(instrumente),
        "warnung": sum(1 for _, b in berichte if b.severity is Severity.WARNUNG),
        "hinweis": sum(1 for _, b in berichte if b.severity is Severity.HINWEIS),
    }
    return _render(
        request, "quality.html",
        berichte=berichte, zaehler=zaehler, nur_probleme=nur_probleme,
    )


# -------------------------------------------------------------- Instrument

@router.get("/instrument/{isin}", response_class=HTMLResponse)
def instrument_detail(request: Request, isin: str, strategie: str = ""):
    from .charts import candlestick

    state = _state(request)
    instrument = state.instruments.get(isin)
    if instrument is None:
        return RedirectResponse("/universe", status_code=303)

    frame = state.cache.bars_in_base_currency(instrument)
    chart = '<p class="muted">Noch keine Kursdaten geladen.</p>'
    evaluation = None
    hint = None
    products: list[dict] = []
    metrics: dict = {}
    strategy = state.strategies.get(strategie)

    bericht = check_series(frame, instrument.isin)

    if not frame.empty:
        ctx = IndicatorContext(frame, state.screener._benchmark_series(strategy) if strategy else None)
        overlays = {"EMA 20": ctx.ma("ema", 20), "SMA 50": ctx.ma("sma", 50)}
        if len(frame) > 200:
            overlays["SMA 200"] = ctx.ma("sma", 200)

        close = float(ctx.close.iloc[-1])
        marken: list[tuple[str, float, str]] = []
        if strategy is not None:
            atr = float(ctx.atr(strategy.risk.atr_period).iloc[-1])
            stop_kurs = close - strategy.risk.stop_atr_factor * atr
            ziel_kurs = close + strategy.risk.target_atr_factor * atr
            marken = [
                (f"Einstieg {close:,.2f}".replace(",", "."), close, "einstieg"),
                (f"Stop {stop_kurs:,.2f}".replace(",", "."), stop_kurs, "stop"),
                (f"Ziel {ziel_kurs:,.2f}".replace(",", "."), ziel_kurs, "ziel"),
            ]
        chart = candlestick(frame, overlays, title=instrument.name, levels=marken)
        metrics = {
            "Kurs (EUR)": round(close, 2),
            "RSI(14)": _fmt(ctx.rsi(14).iloc[-1]),
            "RSI(2)": _fmt(ctx.rsi(2).iloc[-1]),
            "ADX(14)": _fmt(ctx.adx(14).iloc[-1]),
            "ATR(14) in %": _fmt(ctx.atr_pct(14).iloc[-1]),
            "Rel. Volumen": _fmt(ctx.relative_volume(20).iloc[-1]),
            # Kompakt: 268 Mio. statt 268.475.928,00
            "Umsatz 20 Tage (EUR)": _compact(ctx.turnover(20).iloc[-1]),
            "Abstand 52W-Hoch in %": _fmt(ctx.distance_to_high(252).iloc[-1]),
            "Performance 20 Tage in %": _fmt(ctx.roc(20).iloc[-1]),
            "Performance 126 Tage in %": _fmt(ctx.roc(126).iloc[-1]),
            "Volatilitaet p.a. in %": _fmt(ctx.realized_vol(60).iloc[-1]),
        }

        if strategy is not None:
            evaluation = strategy.evaluate(ctx)
            hint = leverage_hint(close, stop_kurs, Direction(strategy.direction))
            adx_value = ctx.adx(14).iloc[-1]
            products = products_for(strategy.horizon, float(adx_value) if adx_value == adx_value else None)

    return _render(
        request, "instrument.html",
        instrument=instrument, chart=chart, metrics=metrics, frame_len=len(frame),
        strategy=strategy, strategie=strategie, evaluation=evaluation,
        hits=evaluation.hits_at(-1) if evaluation else [],
        hint=hint, products=products, risks=GENERAL_RISKS, bericht=bericht,
        zahlen_in_tagen=instrument.earnings_in_days(),
        zahlen_kritisch=(
            strategy is not None
            and instrument.earnings_in_days() is not None
            and 0 <= instrument.earnings_in_days() <= strategy.risk.max_holding_days * 1.5
        ),
        tr_hint=tr_search_hint(instrument.isin, instrument.name),
        issuers=state.issuers, watched=instrument.isin in set(state.watchlist.isins()),
    )


# --------------------------------------------------------------- Watchlist

@router.get("/watchlist", response_class=HTMLResponse)
def watchlist(request: Request):
    state = _state(request)
    return _render(request, "watchlist.html", entries=state.watchlist.entries())


@router.post("/watchlist/add")
def watchlist_add(request: Request, isin: str = Form(...), zurueck: str = Form(default="/watchlist")):
    state = _state(request)
    instrument = state.instruments.get(isin.strip())
    # Nur was im Universum steht, kann auf die Watchlist - damit bleibt die
    # Anforderung 'nur bei TR handelbar' durchgehend erfuellt.
    if instrument is not None and instrument.tr_status is not TRStatus.UNAVAILABLE:
        state.watchlist.add(instrument.isin)
    return RedirectResponse(zurueck, status_code=303)


@router.post("/watchlist/remove")
def watchlist_remove(request: Request, isin: str = Form(...), zurueck: str = Form(default="/watchlist")):
    _state(request).watchlist.remove(isin.strip())
    return RedirectResponse(zurueck, status_code=303)


# ---------------------------------------------------------------- Universum

@router.get("/universe", response_class=HTMLResponse)
def universe(request: Request, q: str = "", status: str = "", klasse: str = ""):
    state = _state(request)
    instruments = state.instruments.all()
    if q:
        needle = q.lower()
        instruments = [
            i for i in instruments if needle in i.name.lower() or needle in i.isin.lower()
            or needle in i.ticker_yahoo.lower()
        ]
    if status:
        instruments = [i for i in instruments if str(i.tr_status) == status]
    if klasse:
        instruments = [i for i in instruments if str(i.asset_class) == klasse]

    stale_cutoff = date.today() - timedelta(days=state.settings.screening.tr_check_stale_days)
    return _render(
        request, "universe.html",
        instruments=instruments[:600], total=len(instruments),
        q=q, status=status, klasse=klasse, stale_cutoff=stale_cutoff,
        watched=set(state.watchlist.isins()), report=state.universe_report,
    )


@router.post("/universe/{isin}/status")
def set_status(request: Request, isin: str, status: str = Form(...), zurueck: str = Form(default="/universe")):
    state = _state(request)
    try:
        state.instruments.set_tr_status(isin, TRStatus(status))
    except ValueError:
        log.warning("Unbekannter Status '%s' fuer %s ignoriert", status, isin)
    return RedirectResponse(zurueck, status_code=303)


# -------------------------------------------------------------- Trefferquote

@router.get("/trefferquote/{name}", response_class=HTMLResponse)
def backtest(request: Request, name: str):
    state = _state(request)
    strategy = state.strategies.get(name)
    if strategy is None:
        return RedirectResponse("/", status_code=303)
    return _render(
        request, "backtest.html",
        name=name, strategy=strategy, result=state.backtests.load(name),
    )


@router.post("/trefferquote/{name}/run")
def run_backtest(request: Request, name: str):
    _state(request).submit_backtest(name)
    return RedirectResponse(f"/trefferquote/{name}", status_code=303)


# ------------------------------------------------------------------ Export

@router.get("/export/{name}.{fmt}")
def export(request: Request, name: str, fmt: str):
    state = _state(request)
    run = state.runs.latest(name)
    if not run or not run.id:
        return RedirectResponse(f"/screener/{name}", status_code=303)
    signals = state.signals.for_run(run.id, 0)

    if fmt == "xlsx":
        path = to_xlsx(signals, state.settings.export_dir, name)
        if path is None:  # openpyxl fehlt - dann eben CSV
            path = to_csv(signals, state.settings.export_dir, name)
    else:
        path = to_csv(signals, state.settings.export_dir, name)
    return FileResponse(path, filename=path.name)


# --------------------------------------------------------------- Einstellungen

@router.get("/einstellungen", response_class=HTMLResponse)
def settings_view(request: Request):
    state = _state(request)
    return _render(
        request, "settings.html",
        settings=state.settings, next_runs=state.scheduler.next_runs(),
        providers=[p.name for p in state.chain.providers],
        history=state.jobs.history,
    )


def _compact(value) -> str:
    from .app import _money

    return _money(_fmt(value, 0))


def _fmt(value, digits: int = 2):
    try:
        if value != value:  # not-a-number
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None
