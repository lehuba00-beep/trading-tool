"""Universumsliste lesen, schreiben und zusammenfuehren."""

from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path

from ..domain.enums import AssetClass, TRStatus
from ..domain.models import Instrument
from .validate import REQUIRED_COLUMNS, ValidationReport, validate_rows

log = logging.getLogger(__name__)


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load(path: Path) -> tuple[list[Instrument], ValidationReport]:
    """Liste einlesen. Fehlerhafte Zeilen werden uebersprungen, nicht geraten."""
    rows = read_rows(path)
    report = validate_rows(rows)
    bad_lines = {
        int(msg.split()[1].rstrip(":")) for msg in report.errors if msg.startswith("Zeile ")
    }

    instruments: list[Instrument] = []
    for number, row in enumerate(rows, start=2):
        if number in bad_lines:
            continue
        instruments.append(
            Instrument(
                isin=row["isin"].strip(),
                name=row["name"].strip(),
                asset_class=AssetClass(row["asset_class"].strip()),
                ticker_yahoo=(row.get("ticker_yahoo") or "").strip(),
                ticker_stooq=(row.get("ticker_stooq") or "").strip(),
                currency=(row.get("currency") or "EUR").strip() or "EUR",
                exchange=(row.get("exchange") or "").strip(),
                tr_status=TRStatus(row["tr_status"].strip()),
                tr_checked_at=_parse_date(row.get("tr_checked_at")),
                source=(row.get("source") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            )
        )
    return instruments, report


def write(path: Path, instruments: list[Instrument]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        for i in sorted(instruments, key=lambda x: (x.asset_class, x.name)):
            writer.writerow(
                {
                    "isin": i.isin, "name": i.name, "asset_class": str(i.asset_class),
                    "ticker_yahoo": i.ticker_yahoo, "ticker_stooq": i.ticker_stooq,
                    "currency": i.currency, "exchange": i.exchange,
                    "tr_status": str(i.tr_status),
                    "tr_checked_at": i.tr_checked_at.isoformat() if i.tr_checked_at else "",
                    "source": i.source, "notes": i.notes,
                }
            )


def merge(existing: list[Instrument], incoming: list[Instrument]) -> list[Instrument]:
    """Import zusammenfuehren. Handarbeit gewinnt gegen Liste.

    Ein bereits geprueftes oder als nicht handelbar markiertes Instrument darf
    durch einen erneuten Import nicht zurueckgesetzt werden - sonst waere jede
    Aktualisierung der Quelllisten ein Rueckschritt.
    """
    by_key = {i.isin: i for i in existing}
    for candidate in incoming:
        current = by_key.get(candidate.isin)
        if current is None:
            by_key[candidate.isin] = candidate
            continue
        if current.tr_status in (TRStatus.VERIFIED, TRStatus.UNAVAILABLE):
            candidate.tr_status = current.tr_status
            candidate.tr_checked_at = current.tr_checked_at
        candidate.notes = current.notes or candidate.notes
        by_key[candidate.isin] = candidate
    return list(by_key.values())


def _parse_date(value: str | None) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        log.warning("Ungueltiges Datum '%s' ignoriert", value)
        return None
