"""Verweise auf Produktfinder der Emittenten.

Bewusst datengetrieben: Die Adressen stehen in ``config/issuers.yaml`` und
lassen sich ohne Codeaenderung anpassen. Emittentenseiten werden umgebaut, und
ein fest verdrahteter Link ist dann eine Sackgasse.

Verlinkt wird jeweils der Produktfinder, nicht ein einzelnes Produkt: Eine
belastbare, dokumentierte Abfrage einzelner Zertifikate bieten die Emittenten
oeffentlich nicht an.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

DEFAULT_ISSUERS = [
    {"name": "HSBC", "url": "https://www.hsbc-zertifikate.de/"},
    {"name": "Vontobel", "url": "https://certificates.vontobel.com/DE/"},
    {"name": "Societe Generale", "url": "https://www.sg-zertifikate.de/"},
    {"name": "BNP Paribas", "url": "https://www.derivate.bnpparibas.com/"},
    {"name": "UniCredit onemarkets", "url": "https://www.onemarkets.de/"},
    {"name": "DZ Bank", "url": "https://www.dzbank-derivate.de/"},
    {"name": "Morgan Stanley", "url": "https://www.morganstanley-zertifikate.de/"},
]


def load_issuers(path: Path | None) -> list[dict]:
    if path and path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            issuers = data.get("issuers")
            if isinstance(issuers, list) and issuers:
                return issuers
        except yaml.YAMLError as exc:
            log.warning("issuers.yaml nicht lesbar (%s) - Vorgaben werden verwendet", exc)
    return DEFAULT_ISSUERS


def tr_search_hint(isin: str, name: str) -> dict:
    """Hinweis zur Pruefung in der Trade-Republic-App.

    Bewusst kein Deeplink: Trade Republic bietet keine dokumentierte,
    stabile Adresse zum Nachschlagen eines Instruments. Statt einen
    zu erfinden, wird die ISIN zum Kopieren angeboten.
    """
    return {
        "isin": isin,
        "name": name,
        "hinweis": (
            "In der Trade-Republic-App nach dieser ISIN suchen und danach hier "
            "auf 'Bei TR geprueft' klicken."
        ),
    }
