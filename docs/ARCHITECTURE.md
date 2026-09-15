# Architektur

**Stand: umgesetzt.** Abschnitt 10 listet die Stellen, an denen die Umsetzung
vom ursprünglichen Vorschlag abweicht, und warum.

## 1. Leitgedanken

1. **Kern ohne UI.** Datenbeschaffung, Indikatoren, Regelwerk und Screener sind
   eine reine Python-Bibliothek ohne UI-Abhängigkeit. Die Oberfläche ist nur ein
   Konsument. Damit sind CLI-Betrieb, Tests, Batch-Läufe und ein späterer
   UI-Wechsel ohne Umbau möglich.
2. **Offline-fähig und reproduzierbar.** Jeder Kursabruf landet in einem lokalen
   Cache. Ein Screening-Lauf ist ohne Netz wiederholbar und liefert dasselbe
   Ergebnis – Voraussetzung für sinnvolle Tests und für die Nachvollziehbarkeit
   eines Signals von gestern.
3. **Regeln als Konfiguration, nicht als Code.** Die drei Strategien sind
   YAML-Profile aus benannten Regelbausteinen. Schwellenwerte ändern heißt
   Datei editieren, nicht neu bauen.
4. **Eine Datenquelle ist austauschbar.** Alle Provider hinter einem Protokoll;
   yfinance ist ein Lieferant, keine Architekturentscheidung. Das ist wichtig,
   weil die kostenlosen Quellen erfahrungsgemäß unangekündigt brechen.
5. **Wenig Abhängigkeiten.** Alles, was mit PyInstaller unter Windows Ärger
   macht (C-Extensions, Node-Buildchains), wird vermieden.

## 2. Tech-Stack (Empfehlung)

| Bereich | Empfehlung | Begründung / Alternativen |
|---|---|---|
| Sprache | Python 3.12 | Ökosystem für Finanzdaten; PyInstaller-tauglich |
| Daten | pandas, numpy | Standard; Indikatoren vektorisiert |
| Provider | `yfinance` (primär), Stooq-CSV (Fallback/Kreuzcheck), CSV-Import | s. DATA_SOURCES.md; Wechsel auf bezahlte Quelle ist eine Modul-Änderung |
| Indikatoren | **eigenes Modul** in pandas | TA-Lib braucht C-Build (Windows-Hürde), `pandas-ta` ist wartungsschwach. ~15 Funktionen sind überschaubar und gegen Referenzwerte testbar |
| Persistenz | SQLite (`sqlite3`, ohne ORM) | eine Datei, kein Server, PyInstaller-freundlich, ausreichend für Tagesbalken |
| Konfiguration | YAML + `pydantic` | Validierung mit klaren Fehlermeldungen statt stiller Defaults |
| Scheduler | `APScheduler` (in-process) | periodischer Refresh ohne Windows-Task-Scheduler |
| UI | **FastAPI + Jinja2 + HTMX**, im Browser | Tabellen/Charts billig, kein Node-Build, PyInstaller unkritisch. Alternative: PySide6 (nativer, aber Charting/Tabellen deutlich aufwändiger, ~150–250 MB Build). Tkinter: für sortier-/filterbare Tabellen mit Charts zu dünn |
| Charts | Lightweight-Charts oder Plotly (lokal eingebunden) | Candlesticks + Indikator-Overlays, keine CDN-Abhängigkeit im Offline-Betrieb |
| Export | CSV nativ, XLSX via `openpyxl` | Weiterverarbeitung in Excel |
| Tests | `pytest` + Golden-Files | Indikatoren gegen fixe Referenzreihen, Regeln gegen konstruierte Kursverläufe |
| Qualität | `ruff` (Lint+Format), optional `mypy` | eine Abhängigkeit statt drei |
| Paketierung | PyInstaller **one-dir** + `start.bat`, optional Inno Setup | one-file entpackt bei jedem Start pandas/numpy nach %TEMP% → spürbar langsamer Start |

**Warum Web-UI statt Desktop-GUI:** Die Kernansicht ist eine sortier- und
filterbare Trefferliste mit Detail-Chart. In HTML ist das ein Nachmittag, in
Qt eine Woche. Die App bleibt trotzdem lokal: `127.0.0.1`-Bindung, der Launcher
startet Server und öffnet den Browser; von außen ist nichts erreichbar.

## 3. Schichten

```
┌─────────────────────────────────────────────────────────────┐
│ UI (FastAPI + HTMX)   ·   CLI   ·   Export (CSV/XLSX)       │
├─────────────────────────────────────────────────────────────┤
│ Screener                                                    │
│  Engine (Läufe)  ·  Ranking/Scoring  ·  Scheduler           │
├──────────────────────────────┬──────────────────────────────┤
│ Strategien (YAML-Profile)    │ Derivate-Modul               │
│  Regelbausteine · Scoring    │  Hebel-/Barrieren-Rechner     │
│                              │  Emittenten-Deeplinks         │
├──────────────────────────────┴──────────────────────────────┤
│ Indikatoren (trend · momentum · volatility · volume)        │
├─────────────────────────────────────────────────────────────┤
│ Universum (Trade-Republic-Liste, Filter, Validierung)       │
├─────────────────────────────────────────────────────────────┤
│ Storage: SQLite-Cache (Bars, Watchlist, Läufe, Signale)     │
├─────────────────────────────────────────────────────────────┤
│ Provider: yfinance · Stooq · CSV   (austauschbar)           │
└─────────────────────────────────────────────────────────────┘
```

Abhängigkeiten zeigen ausschließlich nach unten. Die Indikator- und
Strategieschicht kennt weder Netzwerk noch Datenbank – sie bekommt einen
DataFrame und gibt Zahlen zurück. Das hält sie testbar.

### Ablauf eines Screening-Laufs

```
Universum laden (TR-Liste, nach Status/Assetklasse gefiltert)
   → Watchlist schneiden
   → je Instrument: Bars aus Cache, fehlende Tage nachladen
   → Indikatoren berechnen (vektorisiert, ein Durchlauf je Instrument)
   → Strategieprofil auswerten: Pflichtregeln (Filter) → Punktregeln
   → Score + ausgelöste Signale + Kennzahlen (ATR-Stop, Abstand 52W-Hoch …)
   → Ergebnis in `runs`/`signals` schreiben
   → UI zeigt gerankte Liste je Horizont
```

## 4. Ordnerstruktur

```
trading-tool/
├─ README.md
├─ pyproject.toml
├─ start_windows.bat                 # Startet App und öffnet den Browser
├─ build/
│  ├─ trading_tool.spec              # PyInstaller (one-dir)
│  └─ build_exe.ps1
├─ config/
│  ├─ settings.example.yaml          # Datenverzeichnis, Provider, Refresh-Intervall
│  └─ strategies/
│     ├─ kurzfristig.yaml
│     ├─ mittelfristig.yaml
│     └─ langfristig.yaml
├─ universe/
│  ├─ tr_universe.csv                # kuratierte TR-Liste, versioniert
│  ├─ sources/                       # Rohimporte (Indexlisten, ETF-Listen)
│  └─ README.md                      # Pflege-Workflow
├─ data/                             # Laufzeit, .gitignore
│  ├─ cache.sqlite
│  └─ exports/
├─ src/trading_tool/
│  ├─ __main__.py                    # Launcher: Server starten, Browser öffnen
│  ├─ config.py                      # pydantic-Settings, Pfadauflösung (auch im .exe-Kontext)
│  ├─ domain/
│  │  ├─ models.py                   # Instrument, Bar, Signal, ScreenResult
│  │  └─ enums.py                    # Horizon, AssetClass, TRStatus, Direction
│  ├─ providers/
│  │  ├─ base.py                     # Protocol: fetch_bars(symbol, start, end) -> DataFrame
│  │  ├─ yfinance_provider.py
│  │  ├─ stooq_provider.py
│  │  ├─ csv_provider.py             # Offline-Betrieb und Testfixtures
│  │  └─ registry.py                 # Auswahl + Fallback-Kette
│  ├─ storage/
│  │  ├─ db.py                       # Schema + Migrationen
│  │  ├─ repositories.py             # bars, watchlist, runs, signals
│  │  └─ cache.py                    # Lückenerkennung, inkrementelles Nachladen
│  ├─ universe/
│  │  ├─ loader.py                   # CSV lesen + validieren
│  │  ├─ validate.py                 # Schema-, Dubletten-, Veraltungsprüfung
│  │  └─ importers/                  # Indexkonstituenten, ETF-Listen
│  ├─ indicators/
│  │  ├─ trend.py                    # SMA, EMA, MACD, ADX
│  │  ├─ momentum.py                 # RSI, ROC, Stochastik, 12-1-Momentum
│  │  ├─ volatility.py               # ATR, Bollinger, Donchian, Squeeze
│  │  └─ volume.py                   # Relatives Volumen, OBV, Turnover
│  ├─ strategies/
│  │  ├─ base.py                     # Rule, RuleResult, Strategy
│  │  ├─ rules.py                    # Regelbausteine (deklarativ, kein eval)
│  │  ├─ loader.py                   # YAML → Strategy
│  │  └─ scoring.py
│  ├─ screener/
│  │  ├─ engine.py
│  │  ├─ ranking.py
│  │  └─ scheduler.py
│  ├─ derivatives/
│  │  ├─ sizing.py                   # Hebel, Barrierenabstand, Positionsgröße
│  │  ├─ deeplinks.py                # Links in Emittenten-Produktfinder
│  │  └─ issuer_import.py            # Ausbaustufe: CSV-Import von Emittentenlisten
│  ├─ backtest/
│  │  └─ forward_returns.py          # Trefferquote historischer Signale
│  ├─ reporting/
│  │  └─ export.py
│  └─ ui/
│     ├─ app.py
│     ├─ routes/                     # watchlist, screener, instrument, settings
│     ├─ templates/
│     └─ static/
├─ tests/
│  ├─ fixtures/                      # Referenz-OHLCV als CSV
│  ├─ test_indicators.py
│  ├─ test_strategies.py
│  ├─ test_universe.py
│  └─ test_screener.py
└─ docs/
```

## 5. Datenmodell (SQLite)

```sql
instruments(
  isin TEXT PRIMARY KEY,
  name TEXT, asset_class TEXT,          -- stock | etf | derivative
  ticker_yahoo TEXT, ticker_stooq TEXT,
  currency TEXT, exchange TEXT,
  tr_status TEXT,                       -- verified | assumed | unavailable | unknown
  tr_checked_at DATE, source TEXT, notes TEXT
)

bars(
  isin TEXT, date DATE, provider TEXT,
  open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL,
  PRIMARY KEY (isin, date, provider)
)

watchlist(isin TEXT PRIMARY KEY, added_at DATE, horizons TEXT, tags TEXT, note TEXT)

runs(id INTEGER PRIMARY KEY, started_at, finished_at, strategy, n_instruments, provider, status)

signals(
  run_id INTEGER, isin TEXT, strategy TEXT, direction TEXT,
  score REAL, triggered_rules JSON, metrics JSON,   -- ATR, RVOL, Abstand 52W-Hoch, Stop-Vorschlag
  PRIMARY KEY (run_id, isin, strategy)
)
```

`bars` mit Provider im Schlüssel: Kursreihen verschiedener Quellen (Xetra vs.
Stooq vs. US-Handelsplatz) weichen voneinander ab und dürfen sich nicht
gegenseitig überschreiben.

**Kursbereinigung:** Für Indikatoren wird die split- und dividendenbereinigte
Reihe verwendet, für angezeigte Kursniveaus und Stop-Vorschläge der
Roh-Schlusskurs. Ohne diese Trennung erzeugt jeder Split ein Phantom-Signal.

## 6. Regelwerk als YAML (Entwurf)

Bewusst **keine frei auswertbaren Ausdrücke** (`eval`) – stattdessen benannte
Bausteine mit Parametern: testbar, in der UI als Formular darstellbar, und ohne
die Möglichkeit, über eine Konfigurationsdatei beliebigen Code auszuführen.

```yaml
name: "Kurzfristig (1–5 Tage)"
horizon: short
directions: [long, short]

universe_filter:
  asset_class: [stock, etf]
  tr_status: [verified, assumed]
  min_avg_turnover_eur: 1_000_000     # Liquidität: sonst rutscht der Spread den Vorteil auf
  min_history_days: 250

rules:
  - type: above_ma                     # Pflichtfilter: kein Long gegen den Trend
    params: {ma: ema, period: 50, on: close}
    required: true
  - type: rsi_below
    params: {period: 2, threshold: 10}
    weight: 25
  - type: relative_volume_above
    params: {lookback: 20, factor: 1.5}
    weight: 20
  - type: donchian_breakout
    params: {period: 20}
    weight: 25
  - type: macd_cross_up
    params: {fast: 12, slow: 26, signal: 9}
    weight: 15
  - type: distance_to_52w_high_below
    params: {max_pct: 10}
    weight: 15

scoring:
  method: weighted_sum                 # Summe der erfüllten Gewichte, auf 0–100 normiert
  min_score: 60

risk:
  stop: {type: atr_multiple, period: 14, factor: 2.0}
  target: {type: atr_multiple, period: 14, factor: 3.0}
  max_holding_days: 10
```

## 7. Windows-Betrieb und Paketierung

* **Entwicklung:** `uv`/`venv` + `start_windows.bat`.
* **Auslieferung:** PyInstaller one-dir → `TradingTool/TradingTool.exe`.
  Beim ersten Start wird `%LOCALAPPDATA%\TradingTool\` für `cache.sqlite`,
  Einstellungen und Exporte angelegt; Konfiguration und Universum werden als
  Datendateien mitgeliefert und beim Start dorthin kopiert, damit Nutzeränderungen
  ein Update überleben.
* **Fallstricke, die eingeplant sind:** Pfadauflösung unter `sys._MEIPASS`,
  pandas/numpy-Hidden-Imports, freie Portwahl statt fest 8000, und ein
  SmartScreen-Hinweis beim ersten Start unsignierter Exen (nur Kosmetik, aber
  erklärungsbedürftig).

## 8. Ausbaustufen

| Stufe | Inhalt | Ergebnis |
|---|---|---|
| **M0** | Projektgerüst, Config, SQLite-Schema, Provider yfinance + Stooq, Universum-Loader | `screen --strategy kurzfristig` liefert CSV |
| **M1** | Indikatoren + drei Strategieprofile + Scoring + Tests | belastbare Signale |
| **M2** | Web-UI: Watchlist, Trefferliste je Horizont, Detailansicht mit Chart | bedienbares Tool |
| **M3** | Scheduler, Auto-Refresh, Export, Signal-Historie | Alltagstauglichkeit |
| **M4** | Derivate-Modul: Hebel-/Barrieren-Rechner, Emittenten-Deeplinks | Brücke zu KO/OS |
| **M5** | PyInstaller-Build, Launcher, Ersteinrichtung | verteilbare .exe |
| **M6** | optional: Trefferquoten-Auswertung, Fundamentaldaten, Import von Emittenten-CSV | Qualitätssicherung |

M0–M2 sind der belastbare Kern; alles danach ist additiv und ändert die
Architektur nicht mehr.

## 9. Bewusst ausgeklammert

Keine Broker-Anbindung, keine Orderübermittlung, keine Kontodaten, kein
Portfoliotracking in v1. Das Tool berechnet Kennzahlen und zeigt regelbasierte
Signale; die Bewertung und jede Entscheidung liegen beim Nutzer.


## 10. Abweichungen vom ursprünglichen Vorschlag

| Punkt | Vorschlag | Umgesetzt | Grund |
|---|---|---|---|
| Interaktivität | HTMX einbinden | 30 Zeilen eigenes Polling-Skript | Gebraucht wird genau ein Verhalten: ein Element regelmäßig nachladen. Eine Bibliothek dafür mitzuliefern wäre unverhältnismäßig – und sie müsste mitgeliefert werden, damit die App offline läuft |
| Charts | Lightweight-Charts oder Plotly | Serverseitig gezeichnetes SVG | Kein CDN, keine JS-Abhängigkeit, nichts für PyInstaller. Kerzen, Volumen und Overlays sind knapp 100 Zeilen |
| Profile | drei (ein kurzfristiges) | fünf | Rücksetzer und Ausbruch sind gegensätzliche Ansätze und neutralisieren sich in einem gemeinsamen Score. Dazu Swing als eigenes Profil für 1–4 Wochen |
| Trefferquote | M6, optional | in v1 | Auf Wunsch vorgezogen. Das hat die Regelschnittstelle geprägt: Jede Regel liefert eine **boolesche Zeitreihe** statt eines Einzelwerts, damit Screening und Auswertung dieselbe Logik nutzen |
| Regelformat | Ausdrücke in YAML | benannte Bausteine mit Parametern | Kein `eval` aus einer Konfigurationsdatei, einzeln testbar, in der Oberfläche als Formular darstellbar |
| Positionsgrößen | Rechner vorgesehen | entfällt | Abgewählt. ATR-Stop und Zielzone bleiben als reine Kursabstände – die Knock-Out-Mathematik braucht sie |
| Windows-Build | lokal mit PyInstaller | GitHub-Actions-Windows-Runner | PyInstaller kann nicht plattformübergreifend bauen, und auf dem Zielrechner ist kein Python installiert |
| Abhängigkeiten | – | `tzdata` ergänzt | Windows bringt keine System-Zeitzonendatenbank mit; ohne sie scheitert `zoneinfo("Europe/Berlin")` und damit die gesamte Zeitsteuerung |

## 11. Was geprüft ist – und was nicht

**Geprüft ohne Netz** (131 Tests, reproduzierbar, jeder echte Kursabruf ist im
Testlauf gesperrt und schlägt laut fehl): Normalisierung der
Provider-Antworten, Wiederholungs- und Rückfalllogik, Cache, EUR-Umrechnung,
Indikatoren gegen von Hand nachrechenbare Fälle, Regelwerk, Scoring, Screening,
Trefferquoten-Auswertung, Derivate-Mathematik, Oberfläche.

**Geprüft auf Windows** (GitHub-Actions-Runner, bei jedem Push): Linter, alle
Tests, Prüfung der Universumsliste, PyInstaller-Bau – und danach ein echter
Start der gebauten Exe. Sowohl die Kommandozeile als auch die Oberfläche: Der
Server wird gestartet, es wird auf seine Antwort gewartet, und Trefferliste,
Universum, Einstellungen, Stylesheet und Skript werden einzeln abgerufen. Bei
PyInstaller fehlen genau solche mitgelieferten Dateien gern im Bundle, und ein
Build, der nur fehlerfrei durchläuft, sagt darüber nichts.

**Nicht geprüft: ein echter Kursabruf.** Die Entwicklungsumgebung hatte keinen
Netzzugriff auf Yahoo und Stooq (der Proxy blockt beide), und die Tests sind
bewusst so gebaut, dass sie ohne Netz auskommen. Der erste scharfe Abruf findet
auf dem Zielrechner statt. Falls dort etwas klemmt, steht die Ursache im
Protokoll (`trading-tool.log`); `TradingTool.exe screen -s swing -v` zeigt sie
direkt in der Konsole.

Das ist keine Nachlässigkeit, sondern eine Abwägung: Tests, die gegen eine
fremde Live-Schnittstelle laufen, schlagen irgendwann aus Gründen fehl, die
nichts mit dem Code zu tun haben. Der Preis dafür ist, dass die Schnittstelle
selbst erst im Betrieb geprüft wird.

### Was die Windows-Builds tatsächlich gefunden haben

Vier Anläufe bis zum grünen Build – jeder Fehlschlag war echt und keiner davon
hier reproduzierbar gewesen, bevor der Runner ihn gezeigt hat:

1. **Nicht deklarierte Abhängigkeit.** Der Testclient von Starlette lädt seinen
   HTTP-Client zur Laufzeit nach; lokal war er von Hand installiert, in
   `pyproject.toml` stand er nicht. → `tests/test_packaging.py` prüft jetzt jeden
   Fremdimport gegen die Deklaration.
2. **Nicht beendeter Arbeitsthread.** `JobRunner` startete je Anwendungsinstanz
   einen Thread, den `close()` nie beendet hat. In der Anwendung gibt es nur
   eine Instanz – im Testlauf sammelten sich Dutzende an und der Abbau hing.
3. **Ein Test mit echtem Netzabruf.** Ohne Netz scheiterte er sofort und lief
   grün durch; mit Netz begann er, hunderte Titel zu laden. → Netzsperre im
   Testlauf.
4. **Startskript.** PyInstaller führt sein Einstiegsskript als `__main__` aus,
   nicht als Modul eines Pakets – jeder relative Import scheiterte. Die Exe war
   fertig gebaut und startete nicht. → `build/entry.py`, plus ein Test, der
   diese Startbedingung ohne PyInstaller nachstellt.
