"""Universumsliste: Pruefsummen, Validierung, Zusammenfuehren."""

from __future__ import annotations

from datetime import date

from trading_tool.domain.enums import AssetClass, TRStatus
from trading_tool.domain.models import Instrument
from trading_tool.storage.repositories import InstrumentRepo
from trading_tool.universe import isin_checksum_valid, load, merge, validate_rows, write


def test_pruefziffer_erkennt_echte_isins():
    for isin in ["DE0007164600", "US0378331005", "IE00B4L5Y983", "NL0000235190",
                 "CH0038863350", "GB00B10RZP78"]:
        assert isin_checksum_valid(isin), isin


def test_pruefziffer_erkennt_tippfehler():
    """Faengt keine falsche, aber gueltige ISIN - wohl aber den haeufigsten
    Fehler einer handgepflegten Liste."""
    for isin in ["DE0007164601", "US0378331006", "DE000716460", "XX0007164600", ""]:
        assert not isin_checksum_valid(isin), isin


def test_synthetische_schluessel_sind_von_der_pruefung_ausgenommen():
    report = validate_rows([_row(isin="IDX_GDAXI", asset_class="index")])
    assert report.ok, report.errors


def test_validierung_meldet_zeilennummer_bei_falscher_isin():
    report = validate_rows([_row(), _row(isin="DE0007164601")])
    assert not report.ok
    assert "Zeile 3" in report.errors[0]


def test_validierung_meldet_dubletten():
    report = validate_rows([_row(), _row()])
    assert any("doppelt" in e for e in report.errors)


def test_validierung_warnt_bei_fehlendem_ticker():
    report = validate_rows([_row(ticker_yahoo="")])
    assert report.ok
    assert any("ohne Yahoo-Ticker" in w for w in report.warnings)


def test_schreiben_und_lesen_erhaelt_alle_felder(tmp_path):
    original = Instrument(
        isin="DE0007164600", name="SAP", asset_class=AssetClass.STOCK,
        ticker_yahoo="SAP.DE", ticker_stooq="sap.de", currency="EUR", exchange="XETRA",
        tr_status=TRStatus.VERIFIED, tr_checked_at=date(2026, 1, 15), source="test",
        notes="Notiz",
    )
    path = tmp_path / "u.csv"
    write(path, [original])
    geladen, report = load(path)
    assert report.ok
    assert geladen[0] == original


def test_fehlerhafte_zeilen_werden_uebersprungen_nicht_geraten(tmp_path):
    path = tmp_path / "u.csv"
    path.write_text(
        "isin,name,asset_class,ticker_yahoo,ticker_stooq,currency,exchange,"
        "tr_status,tr_checked_at,source,notes\n"
        "DE0007164600,SAP,stock,SAP.DE,,EUR,XETRA,assumed,,test,\n"
        "DE0007164601,Tippfehler,stock,XXX.DE,,EUR,XETRA,assumed,,test,\n",
        encoding="utf-8",
    )
    instruments, report = load(path)
    assert len(instruments) == 1
    assert instruments[0].name == "SAP"
    assert not report.ok


def test_merge_behaelt_handarbeit():
    """Ein erneuter Import darf eine geprueft-Markierung nicht zuruecksetzen."""
    geprueft = Instrument(isin="DE0007164600", name="SAP", asset_class=AssetClass.STOCK,
                          tr_status=TRStatus.VERIFIED, tr_checked_at=date(2026, 1, 1))
    importiert = Instrument(isin="DE0007164600", name="SAP SE", asset_class=AssetClass.STOCK,
                            tr_status=TRStatus.ASSUMED)
    ergebnis = merge([geprueft], [importiert])[0]
    assert ergebnis.tr_status is TRStatus.VERIFIED
    assert ergebnis.tr_checked_at == date(2026, 1, 1)
    assert ergebnis.name == "SAP SE", "Stammdaten sollen sich aktualisieren"


def test_merge_behaelt_auch_nicht_handelbar():
    markiert = Instrument(isin="DE0007164600", name="SAP", asset_class=AssetClass.STOCK,
                          tr_status=TRStatus.UNAVAILABLE)
    importiert = Instrument(isin="DE0007164600", name="SAP", asset_class=AssetClass.STOCK,
                            tr_status=TRStatus.ASSUMED)
    assert merge([markiert], [importiert])[0].tr_status is TRStatus.UNAVAILABLE


def test_datenbank_import_setzt_geprueft_nicht_zurueck(conn):
    repo = InstrumentRepo(conn)
    repo.upsert_many([Instrument(isin="DE0007164600", name="SAP",
                                 asset_class=AssetClass.STOCK, tr_status=TRStatus.ASSUMED)])
    repo.set_tr_status("DE0007164600", TRStatus.VERIFIED)
    repo.upsert_many([Instrument(isin="DE0007164600", name="SAP SE",
                                 asset_class=AssetClass.STOCK, tr_status=TRStatus.ASSUMED)])
    instrument = repo.get("DE0007164600")
    assert instrument.tr_status is TRStatus.VERIFIED
    assert instrument.name == "SAP SE"


def test_mitgelieferte_liste_ist_fehlerfrei():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "universe" / "tr_universe.csv"
    instruments, report = load(path)
    assert report.ok, report.errors[:5]
    assert len(instruments) > 150
    assert any(i.asset_class is AssetClass.ETF for i in instruments)
    assert any(i.isin == "IDX_MSCIWORLD" for i in instruments), "Vergleichsreihe fehlt"
    # Indizes duerfen nie als handelbar erscheinen
    for i in instruments:
        if i.asset_class is AssetClass.INDEX:
            assert i.tr_status is TRStatus.UNAVAILABLE, i.isin


def _row(**overrides) -> dict:
    row = {
        "isin": "DE0007164600", "name": "SAP", "asset_class": "stock",
        "ticker_yahoo": "SAP.DE", "ticker_stooq": "sap.de", "currency": "EUR",
        "exchange": "XETRA", "tr_status": "assumed", "tr_checked_at": "",
        "source": "test", "notes": "",
    }
    row.update(overrides)
    return row
