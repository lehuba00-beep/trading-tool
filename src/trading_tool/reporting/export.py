"""Export der Trefferlisten."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from ..domain.models import Signal

BASE_COLUMNS = [
    "isin", "name", "strategie", "horizont", "richtung", "score", "stand",
    "vorlaeufig", "tr_status", "ausgeloeste_regeln", "fehlende_regeln",
]

METRIC_COLUMNS = [
    "kurs_eur", "atr_pct", "stop", "ziel", "stop_abstand_pct", "rsi_14", "adx_14",
    "rel_volumen", "umsatz_20d_eur", "abstand_52w_hoch_pct", "perf_20d_pct",
    "perf_126d_pct", "vola_ann_pct", "ueberrendite_126d_pp",
]


def signal_rows(signals: list[Signal]) -> list[dict]:
    rows = []
    for s in signals:
        row = {
            "isin": s.isin, "name": s.name, "strategie": s.strategy,
            "horizont": s.horizon.value, "richtung": s.direction.value,
            "score": s.score, "stand": s.as_of.isoformat(),
            "vorlaeufig": "ja" if s.provisional else "nein",
            "tr_status": s.tr_status.value,
            "ausgeloeste_regeln": " | ".join(s.triggered_labels),
            "fehlende_regeln": " | ".join(s.missing_labels),
        }
        row.update({c: s.metrics.get(c) for c in METRIC_COLUMNS})
        rows.append(row)
    return rows


def to_csv(signals: list[Signal], directory: Path, strategy: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = directory / f"screening_{strategy}_{stamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        # utf-8-sig, damit Excel Umlaute beim Doppelklick richtig anzeigt.
        writer = csv.DictWriter(handle, fieldnames=BASE_COLUMNS + METRIC_COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(signal_rows(signals))
    return path


def to_xlsx(signals: list[Signal], directory: Path, strategy: str) -> Path | None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        return None

    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = directory / f"screening_{strategy}_{stamp}.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = strategy[:31]
    columns = BASE_COLUMNS + METRIC_COLUMNS
    sheet.append(columns)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in signal_rows(signals):
        sheet.append([row.get(c) for c in columns])
    sheet.freeze_panes = "A2"
    for index, column in enumerate(columns, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = max(
            12, min(40, len(column) + 4)
        )
    workbook.save(path)
    return path
