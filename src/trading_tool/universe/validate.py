"""Pruefungen fuer die Universumsliste."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
# Instrumente ohne echte ISIN (Indizes) bekommen einen klar erkennbaren
# Ersatzschluessel, damit sie nie mit einem handelbaren Papier verwechselt werden.
SYNTHETIC_PREFIXES = ("IDX_", "YH_")


def is_synthetic_key(key: str) -> bool:
    return key.upper().startswith(SYNTHETIC_PREFIXES)


def isin_checksum_valid(isin: str) -> bool:
    """Pruefziffer nach ISO 6166.

    Faengt keine falsche, aber gueltige ISIN - wohl aber jeden Tippfehler, und
    das ist bei einer handgepflegten Liste der haeufigste Fehler.
    """
    isin = isin.strip().upper()
    if not ISIN_PATTERN.match(isin):
        return False

    digits = "".join(str(int(c, 36)) for c in isin[:-1])
    total = 0
    # Luhn von rechts: jede zweite Ziffer verdoppeln.
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (total + int(isin[-1])) % 10 == 0


@dataclass
class ValidationReport:
    rows: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (
            f"{self.rows} Zeilen, {len(self.errors)} Fehler, {len(self.warnings)} Hinweise"
        )


REQUIRED_COLUMNS = [
    "isin", "name", "asset_class", "ticker_yahoo", "ticker_stooq",
    "currency", "exchange", "tr_status", "tr_checked_at", "source", "notes",
]

VALID_ASSET_CLASSES = {"stock", "etf", "index"}
VALID_TR_STATUS = {"verified", "assumed", "unavailable", "unknown"}


def validate_rows(rows: list[dict]) -> ValidationReport:
    report = ValidationReport(rows=len(rows))
    seen: dict[str, int] = {}

    for number, row in enumerate(rows, start=2):  # Zeile 1 ist die Kopfzeile
        key = (row.get("isin") or "").strip()
        name = (row.get("name") or "").strip()

        if not key:
            report.errors.append(f"Zeile {number}: Schluessel (isin) fehlt")
            continue
        if key in seen:
            report.errors.append(f"Zeile {number}: '{key}' doppelt (zuerst Zeile {seen[key]})")
            continue
        seen[key] = number

        if not name:
            report.errors.append(f"Zeile {number}: Name fehlt fuer {key}")

        if not is_synthetic_key(key) and not isin_checksum_valid(key):
            report.errors.append(
                f"Zeile {number}: '{key}' ist keine gueltige ISIN (Pruefziffer falsch)"
            )

        asset_class = (row.get("asset_class") or "").strip()
        if asset_class not in VALID_ASSET_CLASSES:
            report.errors.append(
                f"Zeile {number}: asset_class '{asset_class}' unbekannt "
                f"({sorted(VALID_ASSET_CLASSES)})"
            )

        status = (row.get("tr_status") or "").strip()
        if status not in VALID_TR_STATUS:
            report.errors.append(
                f"Zeile {number}: tr_status '{status}' unbekannt ({sorted(VALID_TR_STATUS)})"
            )

        if not (row.get("ticker_yahoo") or "").strip():
            report.warnings.append(
                f"Zeile {number}: {key} ohne Yahoo-Ticker - wird nicht gescreent"
            )

        if status == "verified" and not (row.get("tr_checked_at") or "").strip():
            report.warnings.append(
                f"Zeile {number}: {key} ist 'verified', aber ohne Pruefdatum"
            )

    return report
