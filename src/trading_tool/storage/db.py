"""SQLite-Schema und Migrationen.

Eine Datei, kein Server, keine ORM-Schicht. Fuer Tagesbalken ueber ein paar
hundert Titel ist das reichlich dimensioniert und laesst sich mit PyInstaller
ohne Sonderbehandlung ausliefern.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
    isin          TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    asset_class   TEXT NOT NULL,
    ticker_yahoo  TEXT,
    ticker_stooq  TEXT,
    currency      TEXT NOT NULL DEFAULT 'EUR',
    exchange      TEXT,
    tr_status     TEXT NOT NULL DEFAULT 'unknown',
    tr_checked_at TEXT,
    source        TEXT,
    notes         TEXT,
    -- Naechster Termin fuer Quartalszahlen. Das Werkzeug sieht sonst nur
    -- Kurse und kann nicht wissen, dass uebermorgen Zahlen kommen.
    next_earnings TEXT,
    earnings_checked_at TEXT
);

-- Rohkurse in Originalwaehrung. Der Provider gehoert in den Schluessel:
-- Xetra- und Stooq-Reihen weichen voneinander ab und duerfen sich nicht
-- gegenseitig ueberschreiben.
CREATE TABLE IF NOT EXISTS bars (
    isin      TEXT NOT NULL,
    date      TEXT NOT NULL,
    provider  TEXT NOT NULL,
    open      REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL,
    PRIMARY KEY (isin, date, provider)
);
CREATE INDEX IF NOT EXISTS idx_bars_isin_date ON bars (isin, date);

-- Wechselkurse als Einheiten Fremdwaehrung je 1 EUR (wie EURUSD).
CREATE TABLE IF NOT EXISTS fx_rates (
    currency TEXT NOT NULL,
    date     TEXT NOT NULL,
    rate     REAL NOT NULL,
    PRIMARY KEY (currency, date)
);

CREATE TABLE IF NOT EXISTS watchlist (
    isin     TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    horizons TEXT,
    tags     TEXT,
    note     TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy      TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    n_instruments INTEGER DEFAULT 0,
    n_hits        INTEGER DEFAULT 0,
    provider      TEXT,
    status        TEXT DEFAULT 'running',
    message       TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    run_id      INTEGER NOT NULL,
    isin        TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    horizon     TEXT NOT NULL,
    direction   TEXT NOT NULL,
    score       REAL NOT NULL,
    as_of       TEXT NOT NULL,
    provisional INTEGER DEFAULT 0,
    hits        TEXT,
    metrics     TEXT,
    -- Befund der Datenqualitaetspruefung und naechster Zahlentermin: gehoeren
    -- an das Signal, weil beide seine Belastbarkeit betreffen.
    quality       TEXT DEFAULT 'ok',
    quality_notes TEXT,
    earnings_date TEXT,
    PRIMARY KEY (run_id, isin, strategy)
);
CREATE INDEX IF NOT EXISTS idx_signals_run ON signals (run_id, score DESC);

-- Ergebnisse der Trefferquoten-Auswertung, damit die teure Rechnung nicht
-- bei jedem Seitenaufruf wiederholt wird.
CREATE TABLE IF NOT EXISTS backtests (
    strategy    TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (strategy)
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Nachtraeglich hinzugekommene Spalten. SQLite kann sie folgenlos anhaengen;
# eine bestehende Datenbank verliert dabei nichts.
MIGRATIONS: list[tuple[str, str]] = [
    ("instruments", "ALTER TABLE instruments ADD COLUMN next_earnings TEXT"),
    ("instruments", "ALTER TABLE instruments ADD COLUMN earnings_checked_at TEXT"),
    ("signals", "ALTER TABLE signals ADD COLUMN quality TEXT DEFAULT 'ok'"),
    ("signals", "ALTER TABLE signals ADD COLUMN quality_notes TEXT"),
    ("signals", "ALTER TABLE signals ADD COLUMN earnings_date TEXT"),
]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Fehlende Spalten ergaenzen. Liefert die ausgefuehrten Anweisungen."""
    ausgefuehrt = []
    for table, statement in MIGRATIONS:
        spalte = statement.rsplit("ADD COLUMN ", 1)[-1].split()[0]
        if spalte in _existing_columns(conn, table):
            continue
        with conn:
            conn.execute(statement)
        ausgefuehrt.append(statement)
    return ausgefuehrt


def init_db(path: Path) -> sqlite3.Connection:
    conn = connect(path)
    with conn:
        conn.executescript(SCHEMA)
    migrate(conn)
    with conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
    return conn


@contextmanager
def session(path: Path) -> Iterator[sqlite3.Connection]:
    conn = init_db(path)
    try:
        yield conn
    finally:
        conn.close()
