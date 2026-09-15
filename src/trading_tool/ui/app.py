"""FastAPI-Anwendung.

Bindet ausschliesslich auf 127.0.0.1. Die Oberflaeche laeuft im Browser, die
Anwendung bleibt aber lokal - von aussen ist nichts erreichbar.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import Settings, load_settings
from ..domain.enums import TRStatus
from .state import AppState, static_dir, templates_dir
from .views import router

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state: AppState = app.state.app
        state.import_universe()
        state.scheduler.start()
        yield
        state.close()

    app = FastAPI(title="Trading-Tool", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.app = AppState(settings)

    templates = Jinja2Templates(directory=str(templates_dir()))
    templates.env.filters["zahl"] = _number
    templates.env.filters["geld"] = _money
    templates.env.globals["TRStatus"] = TRStatus
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(static_dir())), name="static")
    app.include_router(router)
    return app


def _number(value, digits: int = 2) -> str:
    """Zahl in deutscher Schreibweise: Punkt als Tausender-, Komma als Dezimaltrenner."""
    if value is None or value == "":
        return "-"
    try:
        text = f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)
    return text.replace(",", " ").replace(".", ",").replace(" ", ".")


def _money(value) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 1_000_000:
        return f"{_number(number / 1_000_000, 1)} Mio."
    if abs(number) >= 1_000:
        return f"{_number(number / 1_000, 0)} Tsd."
    return _number(number, 2)
