"""Datenzugriff. Jede Tabelle bekommt genau eine Zustaendigkeit."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

import pandas as pd

from ..domain.enums import AssetClass, Direction, Horizon, TRStatus
from ..domain.models import Instrument, RuleHit, ScreenRun, Signal


def _to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class InstrumentRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_many(self, instruments: list[Instrument]) -> int:
        rows = [
            (
                i.isin, i.name, str(i.asset_class), i.ticker_yahoo, i.ticker_stooq,
                i.currency, i.exchange, str(i.tr_status),
                i.tr_checked_at.isoformat() if i.tr_checked_at else None,
                i.source, i.notes,
            )
            for i in instruments
        ]
        with self.conn:
            # Ein bereits geprueftes Instrument darf durch einen erneuten Import
            # nicht auf 'assumed' zurueckfallen - Handarbeit gewinnt gegen Liste.
            self.conn.executemany(
                """
                INSERT INTO instruments
                    (isin, name, asset_class, ticker_yahoo, ticker_stooq, currency,
                     exchange, tr_status, tr_checked_at, source, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(isin) DO UPDATE SET
                    name = excluded.name,
                    asset_class = excluded.asset_class,
                    ticker_yahoo = excluded.ticker_yahoo,
                    ticker_stooq = excluded.ticker_stooq,
                    currency = excluded.currency,
                    exchange = excluded.exchange,
                    tr_status = CASE
                        WHEN instruments.tr_status IN ('verified','unavailable')
                        THEN instruments.tr_status ELSE excluded.tr_status END,
                    tr_checked_at = COALESCE(instruments.tr_checked_at, excluded.tr_checked_at),
                    source = excluded.source,
                    notes = excluded.notes
                """,
                rows,
            )
        return len(rows)

    def _row_to_instrument(self, r: sqlite3.Row) -> Instrument:
        return Instrument(
            isin=r["isin"], name=r["name"], asset_class=AssetClass(r["asset_class"]),
            ticker_yahoo=r["ticker_yahoo"] or "", ticker_stooq=r["ticker_stooq"] or "",
            currency=r["currency"], exchange=r["exchange"] or "",
            tr_status=TRStatus(r["tr_status"]), tr_checked_at=_to_date(r["tr_checked_at"]),
            source=r["source"] or "", notes=r["notes"] or "",
        )

    def get(self, isin: str) -> Instrument | None:
        row = self.conn.execute("SELECT * FROM instruments WHERE isin = ?", (isin,)).fetchone()
        return self._row_to_instrument(row) if row else None

    def all(self) -> list[Instrument]:
        rows = self.conn.execute("SELECT * FROM instruments ORDER BY name").fetchall()
        return [self._row_to_instrument(r) for r in rows]

    def screenable(
        self, tr_status: list[str], asset_classes: list[str] | None = None
    ) -> list[Instrument]:
        status_slots = ",".join("?" * len(tr_status))
        q = (
            f"SELECT * FROM instruments WHERE tr_status IN ({status_slots}) "
            "AND ticker_yahoo IS NOT NULL AND ticker_yahoo <> ''"
        )
        params: list[str] = list(tr_status)
        if asset_classes:
            class_slots = ",".join("?" * len(asset_classes))
            q += f" AND asset_class IN ({class_slots})"
            params += asset_classes
        rows = self.conn.execute(q + " ORDER BY name", params).fetchall()
        return [self._row_to_instrument(r) for r in rows]

    def set_tr_status(self, isin: str, status: TRStatus) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE instruments SET tr_status = ?, tr_checked_at = ? WHERE isin = ?",
                (str(status), date.today().isoformat(), isin),
            )

    def stale_checks(self, days: int) -> list[Instrument]:
        """Eintraege, deren TR-Pruefung zu alt ist. Produkte verschwinden aus dem
        Handel; eine Liste ohne Verfallsdatum wird still falsch."""
        cutoff = (pd.Timestamp.today() - pd.Timedelta(days=days)).date().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM instruments WHERE tr_status = 'verified' "
            "AND (tr_checked_at IS NULL OR tr_checked_at < ?) ORDER BY tr_checked_at",
            (cutoff,),
        ).fetchall()
        return [self._row_to_instrument(r) for r in rows]


class BarRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, isin: str, provider: str, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        rows = [
            (
                isin, idx.date().isoformat(), provider,
                _f(r.get("open")), _f(r.get("high")), _f(r.get("low")),
                _f(r.get("close")), _f(r.get("adj_close")), _f(r.get("volume")),
            )
            for idx, r in frame.iterrows()
        ]
        with self.conn:
            self.conn.executemany(
                "INSERT INTO bars (isin,date,provider,open,high,low,close,adj_close,volume) "
                "VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(isin,date,provider) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, adj_close=excluded.adj_close, volume=excluded.volume",
                rows,
            )
        return len(rows)

    def load(self, isin: str, provider: str | None = None) -> pd.DataFrame:
        q = "SELECT date, open, high, low, close, adj_close, volume FROM bars WHERE isin = ?"
        params: list[str] = [isin]
        if provider:
            q += " AND provider = ?"
            params.append(provider)
        q += " ORDER BY date"
        frame = pd.read_sql_query(q, self.conn, params=params, parse_dates=["date"])
        if frame.empty:
            return frame
        return frame.set_index("date")

    def last_date(self, isin: str, provider: str) -> date | None:
        row = self.conn.execute(
            "SELECT MAX(date) AS d FROM bars WHERE isin = ? AND provider = ?", (isin, provider)
        ).fetchone()
        return _to_date(row["d"]) if row and row["d"] else None

    def coverage(self) -> dict[str, int]:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT isin) AS n_isin, COUNT(*) AS n_bars FROM bars"
        ).fetchone()
        return {"instruments": row["n_isin"], "bars": row["n_bars"]}


class FxRepo:
    """Wechselkurse als Einheiten Fremdwaehrung je 1 EUR."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, currency: str, series: pd.Series) -> int:
        rows = [(currency, idx.date().isoformat(), float(v)) for idx, v in series.dropna().items()]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany(
                "INSERT INTO fx_rates (currency,date,rate) VALUES (?,?,?) "
                "ON CONFLICT(currency,date) DO UPDATE SET rate = excluded.rate",
                rows,
            )
        return len(rows)

    def load(self, currency: str) -> pd.Series:
        frame = pd.read_sql_query(
            "SELECT date, rate FROM fx_rates WHERE currency = ? ORDER BY date",
            self.conn, params=[currency], parse_dates=["date"],
        )
        if frame.empty:
            return pd.Series(dtype="float64")
        return frame.set_index("date")["rate"]

    def last_date(self, currency: str) -> date | None:
        row = self.conn.execute(
            "SELECT MAX(date) AS d FROM fx_rates WHERE currency = ?", (currency,)
        ).fetchone()
        return _to_date(row["d"]) if row and row["d"] else None


class WatchlistRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, isin: str, horizons: list[str] | None = None, note: str = "") -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO watchlist (isin, added_at, horizons, note) VALUES (?,?,?,?) "
                "ON CONFLICT(isin) DO UPDATE SET horizons = excluded.horizons, note = excluded.note",
                (isin, date.today().isoformat(), ",".join(horizons or []), note),
            )

    def remove(self, isin: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM watchlist WHERE isin = ?", (isin,))

    def isins(self) -> list[str]:
        return [r["isin"] for r in self.conn.execute("SELECT isin FROM watchlist").fetchall()]

    def entries(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT w.isin, w.added_at, w.horizons, w.note, i.name, i.asset_class, i.tr_status "
            "FROM watchlist w LEFT JOIN instruments i ON i.isin = w.isin ORDER BY i.name"
        ).fetchall()
        return [dict(r) for r in rows]


class RunRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def start(self, strategy: str, provider: str) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO runs (strategy, started_at, provider, status) VALUES (?,?,?,'running')",
                (strategy, datetime.now().isoformat(timespec="seconds"), provider),
            )
        return int(cur.lastrowid)

    def finish(self, run_id: int, n_instruments: int, n_hits: int, status: str = "ok",
               message: str = "") -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE runs SET finished_at = ?, n_instruments = ?, n_hits = ?, "
                "status = ?, message = ? WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), n_instruments, n_hits,
                 status, message, run_id),
            )

    def latest(self, strategy: str) -> ScreenRun | None:
        row = self.conn.execute(
            "SELECT * FROM runs WHERE strategy = ? AND status = 'ok' "
            "ORDER BY id DESC LIMIT 1", (strategy,)
        ).fetchone()
        if not row:
            return None
        return ScreenRun(
            id=row["id"], strategy=row["strategy"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            n_instruments=row["n_instruments"], n_hits=row["n_hits"],
            provider=row["provider"] or "", status=row["status"], message=row["message"] or "",
        )

    def prune(self, keep_per_strategy: int = 30) -> int:
        """Alte Laeufe entfernen, damit die Datei nicht unbegrenzt waechst."""
        with self.conn:
            cur = self.conn.execute(
                """
                DELETE FROM runs WHERE id IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY strategy ORDER BY id DESC) AS rn FROM runs
                    ) WHERE rn > ?
                )
                """,
                (keep_per_strategy,),
            )
            self.conn.execute("DELETE FROM signals WHERE run_id NOT IN (SELECT id FROM runs)")
        return cur.rowcount


class SignalRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save_many(self, run_id: int, signals: list[Signal]) -> int:
        rows = [
            (
                run_id, s.isin, s.strategy, str(s.horizon), str(s.direction), s.score,
                s.as_of.isoformat(), int(s.provisional),
                json.dumps(_hits_as_dicts(s.hits), ensure_ascii=False),
                json.dumps(s.metrics, ensure_ascii=False),
            )
            for s in signals
        ]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany(
                "INSERT INTO signals (run_id,isin,strategy,horizon,direction,score,as_of,"
                "provisional,hits,metrics) VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(run_id,isin,strategy) DO UPDATE SET score = excluded.score",
                rows,
            )
        return len(rows)

    def for_run(self, run_id: int, min_score: float = 0.0) -> list[Signal]:
        rows = self.conn.execute(
            "SELECT s.*, i.name, i.tr_status FROM signals s "
            "LEFT JOIN instruments i ON i.isin = s.isin "
            "WHERE s.run_id = ? AND s.score >= ? ORDER BY s.score DESC",
            (run_id, min_score),
        ).fetchall()
        out = []
        for r in rows:
            out.append(
                Signal(
                    isin=r["isin"], name=r["name"] or r["isin"], strategy=r["strategy"],
                    horizon=Horizon(r["horizon"]), direction=Direction(r["direction"]),
                    score=r["score"], as_of=date.fromisoformat(r["as_of"]),
                    hits=[RuleHit(**h) for h in json.loads(r["hits"] or "[]")],
                    metrics=json.loads(r["metrics"] or "{}"),
                    tr_status=TRStatus(r["tr_status"] or "unknown"),
                    provisional=bool(r["provisional"]),
                )
            )
        return out


class BacktestRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save(self, strategy: str, payload: dict) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO backtests (strategy, computed_at, payload) VALUES (?,?,?) "
                "ON CONFLICT(strategy) DO UPDATE SET computed_at = excluded.computed_at, "
                "payload = excluded.payload",
                (strategy, datetime.now().isoformat(timespec="seconds"),
                 json.dumps(payload, ensure_ascii=False)),
            )

    def load(self, strategy: str) -> dict | None:
        row = self.conn.execute(
            "SELECT computed_at, payload FROM backtests WHERE strategy = ?", (strategy,)
        ).fetchone()
        if not row:
            return None
        data = json.loads(row["payload"])
        data["computed_at"] = datetime.fromisoformat(row["computed_at"]).strftime(
            "%d.%m.%Y %H:%M"
        )
        return data


def _hits_as_dicts(hits: list[RuleHit]) -> list[dict]:
    return [
        {"rule_id": h.rule_id, "label": h.label, "triggered": h.triggered,
         "weight": h.weight, "required": h.required}
        for h in hits
    ]


def _f(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
