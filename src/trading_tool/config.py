"""Konfiguration und Pfadaufloesung.

Die Pfadaufloesung muss zwei Faelle bedienen: Entwicklung aus dem Repository
heraus und den PyInstaller-Build, bei dem mitgelieferte Dateien
schreibgeschuetzt in einem Temporaerverzeichnis liegen. Nutzerdaten gehoeren in
beiden Faellen in ein beschreibbares Verzeichnis, sonst ueberlebt keine
Aenderung ein Update.
"""

from __future__ import annotations

import os
import sys
from datetime import time
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def bundle_dir() -> Path:
    """Verzeichnis der mitgelieferten Dateien (Vorlagen, Templates, Universum)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    """Beschreibbares Verzeichnis fuer Cache, Einstellungen und Exporte."""
    override = os.environ.get("TRADING_TOOL_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "TradingTool"
    if is_frozen():
        return Path.home() / ".trading-tool"
    return bundle_dir() / "data"


class ProviderSettings(BaseModel):
    primary: str = "yfinance"
    fallback: list[str] = Field(default_factory=lambda: ["stooq"])
    request_pause_seconds: float = 0.4
    """Pause zwischen Abrufen. Die kostenlosen Quellen drosseln undokumentiert;
    ohne Pause endet ein Lauf ueber 300 Titel regelmaessig in leeren Antworten."""
    max_retries: int = 2
    history_days: int = 1500


class ScheduleSettings(BaseModel):
    """Drei Laeufe taeglich, an den Handelszeiten ausgerichtet."""

    enabled: bool = True
    times: list[str] = Field(default_factory=lambda: ["09:30", "14:00", "22:30"])
    timezone: str = "Europe/Berlin"

    @field_validator("times")
    @classmethod
    def _valid_times(cls, v: list[str]) -> list[str]:
        for entry in v:
            hh, _, mm = entry.partition(":")
            time(int(hh), int(mm))  # wirft bei Unsinn
        return v

    def as_hour_minute(self) -> list[tuple[int, int]]:
        out = []
        for entry in self.times:
            hh, _, mm = entry.partition(":")
            out.append((int(hh), int(mm)))
        return out


class ScreeningSettings(BaseModel):
    base_currency: str = "EUR"
    """Alle Kurse und Kennzahlen werden hierhin umgerechnet."""
    include_tr_status: list[str] = Field(default_factory=lambda: ["verified", "assumed"])
    tr_check_stale_days: int = 183
    strategies: list[str] = Field(
        default_factory=lambda: [
            "kurz_pullback",
            "kurz_ausbruch",
            "swing",
            "mittelfristig",
            "langfristig",
        ]
    )


class QuoteSettings(BaseModel):
    """Laufend aktualisierte Kurse.

    Ausdruecklich keine Echtzeitkurse: Yahoo liefert je nach Boerse 15 bis 20
    Minuten verzoegert. Die Oberflaeche weist das aus.
    """

    enabled: bool = True
    refresh_seconds: int = 30
    """Wie oft die Oberflaeche nachfragt."""
    ttl_seconds: int = 25
    """Wie lange ein abgerufener Kurs wiederverwendet wird. Knapp unter dem
    Abfrageintervall, damit die Quelle nicht oefter belastet wird als noetig."""
    max_symbols: int = 80
    """Obergrenze je Abruf. Ohne sie waere eine lange Trefferliste der
    schnellste Weg in die Drosselung."""


class EarningsSettings(BaseModel):
    """Termine fuer Quartalszahlen.

    Yahoo liefert sie unvollstaendig und nicht immer zuverlaessig - deshalb
    sind sie ein Hinweis, keine Zusicherung.
    """

    enabled: bool = True
    max_age_days: int = 7
    """Nach dieser Zeit wird ein Termin neu abgefragt."""
    per_run: int = 40
    """Wie viele Titel je Screening-Lauf nachgefragt werden. Begrenzt, damit
    der Lauf nicht an hunderten Zusatzabrufen haengt."""
    warn_within_days: int = 10


class UISettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 0
    """0 = freien Port waehlen. Ein fest verdrahteter Port kollidiert frueher
    oder spaeter mit etwas anderem auf dem Rechner."""
    open_browser: bool = True

    allow_lan: bool = False
    """Zugriff aus dem Heimnetz, etwa vom Handy. Erfordert ein Passwort -
    ohne eines verweigert die Anwendung den Start im Netz."""
    password_hash: str = ""
    """Abgeleitetes Passwort. Klartext wird nie gespeichert."""


class Settings(BaseModel):
    provider: ProviderSettings = Field(default_factory=ProviderSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    screening: ScreeningSettings = Field(default_factory=ScreeningSettings)
    quotes: QuoteSettings = Field(default_factory=QuoteSettings)
    earnings: EarningsSettings = Field(default_factory=EarningsSettings)
    ui: UISettings = Field(default_factory=UISettings)

    # Pfade, zur Laufzeit gesetzt
    data_dir: Path = Field(default_factory=user_data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "cache.sqlite"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def strategy_dir(self) -> Path:
        """Nutzereigene Strategien haben Vorrang vor den mitgelieferten."""
        user = self.data_dir / "strategies"
        return user if user.is_dir() and any(user.glob("*.yaml")) else bundle_dir() / "config" / "strategies"

    @property
    def universe_path(self) -> Path:
        user = self.data_dir / "tr_universe.csv"
        return user if user.exists() else bundle_dir() / "universe" / "tr_universe.csv"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.yaml"


def load_settings() -> Settings:
    data_dir = user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "exports").mkdir(exist_ok=True)

    path = data_dir / "settings.yaml"
    raw: dict = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    settings = Settings(**raw)
    settings.data_dir = data_dir
    return settings


def save_settings(settings: Settings) -> None:
    payload = settings.model_dump(mode="json", exclude={"data_dir"})
    settings.settings_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
