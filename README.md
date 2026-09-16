# Trading-Tool

Lokal unter Windows lauffähiges Analyse- und Screening-Werkzeug für kurz-,
mittel- und langfristige Handelschancen in Aktien und ETFs, beschränkt auf bei
Trade Republic handelbare Wertpapiere, mit rechnerischer Umsetzungshilfe für
Hebelprodukte.

**Keine Broker-Anbindung. Keine Orderausführung. Keine Anlageberatung.**

## Was es tut

* Durchsucht rund 215 Titel nach fünf Regelprofilen und zeigt Treffer mit Score,
  ausgelösten Einzelregeln und Kennzahlen.
* Rechnet alle Kurse nach EUR um – also die Entwicklung, die im Depot ankommt.
* Wertet auf Knopfdruck aus, was historisch nach einem Signal passiert ist, und
  stellt das einer Vergleichsgruppe gegenüber.
* Leitet für Hebelprodukte den maximal sinnvollen Hebel und den
  Mindestabstand der Knock-Out-Schwelle aus der Volatilität ab – ohne einen
  einzigen Zertifikatskurs abzurufen.
* Zeichnet Einstieg, ATR-Stop und Zielzone direkt in den Chart.
* Prüft die Kursreihen auf Datenfehler: veraltete Reihen, fehlerhafte
  Einzelkurse, widersprüchliche Balken.
* Warnt, wenn Quartalszahlen in die geplante Haltedauer fallen.
* Aktualisiert die angezeigten Kurse laufend (verzögert, mit Zeitstempel).
* Läuft dreimal täglich automatisch: 09:30, 14:00, 22:30.

## Schnellstart

**Ohne Python-Installation** (der vorgesehene Weg): Die fertige Anwendung aus
dem GitHub-Actions-Artefakt herunterladen – Anleitung in
[docs/WINDOWS.md](docs/WINDOWS.md). Entpacken, `TradingTool.exe` starten, der
Browser öffnet sich.

**Mit Python 3.11 oder neuer:**

```bash
pip install -e .
trading-tool            # Oberfläche starten
```

Unter Windows genügt ein Doppelklick auf `start_windows.bat`.

Beim ersten Screening werden rund vier Jahre Tagesbalken geladen – das dauert
einige Minuten. Danach nur noch die fehlenden Tage.

## Ohne Oberfläche

```bash
trading-tool universe            # Universumsliste prüfen
trading-tool rules               # Regelbausteine auflisten
trading-tool screen -s swing     # Screening, optional --export
trading-tool backtest -s swing   # Trefferquote historischer Signale
```

## Die fünf Profile

| Profil | Horizont | Ansatz |
|---|---|---|
| `kurz_pullback` | 1–5 Tage | Rücksetzer im intakten Aufwärtstrend (RSI(2) unter SMA-200-Filter) |
| `kurz_ausbruch` | 1–5 Tage | Ausbruch über das 20-Tage-Hoch mit Volumenbestätigung |
| `swing` | 1–4 Wochen | Bestätigter Trend mit frischem Momentumwechsel |
| `mittelfristig` | 1–6 Monate | Trendstruktur 50/200 plus relative Stärke |
| `langfristig` | ab 6 Monaten | 12-1-Momentum unter 200-Tage-Regimefilter |

Rücksetzer und Ausbruch sind bewusst getrennt: In einem gemeinsamen Score
würden sich die gegensätzlichen Ansätze teilweise neutralisieren.

Jedes Profil ist eine YAML-Datei in `config/strategies/` und lässt sich ohne
Neubau anpassen. Eigene Profile im Datenverzeichnis haben Vorrang.

## Dokumentation

| Datei | Inhalt |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Schichtenmodell, Tech-Stack, Ordnerstruktur, Datenmodell, Umsetzungsstand |
| [docs/SIGNALS.md](docs/SIGNALS.md) | Indikator- und Regelkatalog je Zeithorizont, Scoring, Knock-Out-Mathematik |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Kursquellen im Vergleich, Grenzen, Derivate-Datenlage |
| [docs/WINDOWS.md](docs/WINDOWS.md) | Installation, Ablageorte, Betrieb, Fehlersuche |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | Getroffene Entscheidungen und verbleibende offene Punkte |
| [universe/README.md](universe/README.md) | Pflege der Trade-Republic-Liste |

## Entwicklung

```bash
pip install -e ".[dev,xlsx]"
pytest -q          # 110 Tests, ohne Netzzugriff
ruff check src tests
```

## Grenzen, die man kennen sollte

* **Handelbarkeit ist nicht abfragbar.** Trade Republic bietet keine
  Schnittstelle dafür. Die mitgelieferte Liste steht auf `assumed` – vor jeder
  Order in der App nachsehen. Die Oberfläche macht das Nachtragen zu einem Klick.
* **Yahoo ist eine inoffizielle Quelle.** Sie bricht gelegentlich; Stooq springt
  als Rückfall ein. Ein Wechsel auf einen bezahlten Anbieter betrifft ein Modul.
* **Die Trefferquoten-Auswertung schaut zurück, nicht nach vorn.** Delistete
  Titel fehlen in der Datenquelle, Gebühren und Spread sind nicht enthalten, und
  mit genügend Parametervarianten sieht jede Regel irgendwann gut aus.
* **Keine Zertifikatskurse.** Für Hebelprodukte liefert das Werkzeug Mathematik
  und Hinweise, keine Produktdaten.
* **Keine Echtzeitkurse.** Die laufende Aktualisierung zeigt den aktuellsten
  *verfügbaren* Kurs — je nach Börse 15 bis 20 Minuten verzögert. Echte
  Realtime-Daten setzen einen lizenzierten, kostenpflichtigen Feed voraus.
  Abrufzeitpunkt und Verzögerung stehen in der Oberfläche.
* **Quartalstermine sind lückenhaft.** Für ETFs und Indizes gibt es keine, für
  manche Nebenwerte auch nicht. Ein Hinweis, keine Zusicherung.

## Rechtlicher Hinweis

Dieses Werkzeug zeigt Kennzahlen und regelbasierte Signale. Es spricht keine
Empfehlung im Sinne einer Anlageberatung aus, berücksichtigt keine persönlichen
Verhältnisse und hat keine Verbindung zu einem Broker. Jede Handelsentscheidung
trifft ausschließlich der Nutzer. Historische Signale sagen nichts über
künftige Kursentwicklungen aus. Kursdaten ohne Gewähr.
