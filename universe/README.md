# Universumsliste pflegen

`tr_universe.csv` ist die Grundlage des Screenings. Sie beantwortet zwei Fragen:
**Welche Titel werden untersucht** und **wie gut ist belegt, dass sie bei Trade
Republic handelbar sind.**

Die Datei liegt im Git. Jede Aenderung ist damit nachvollziehbar und
rueckgaengig zu machen - der billigste verfuegbare Pruefpfad.

## Spalten

| Spalte | Bedeutung |
|---|---|
| `isin` | Schluessel. Bei Vergleichsindizes ein Ersatzschluessel mit Praefix `IDX_`, weil Indizes keine handelbare ISIN haben |
| `name` | Anzeigename |
| `asset_class` | `stock`, `etf` oder `index` |
| `ticker_yahoo` | Symbol der Primaerquelle. **Ohne dieses Feld wird der Titel nicht gescreent** |
| `ticker_stooq` | Symbol der Rueckfallquelle, klein geschrieben (`sap.de`, `aapl.us`) |
| `currency` | Notierungswaehrung. `GBp` fuer britische Titel in Pence |
| `exchange` | Handelsplatz der Kursdaten |
| `tr_status` | s. unten |
| `tr_checked_at` | Datum der letzten Pruefung |
| `source` | Woher der Eintrag stammt |
| `notes` | Freitext |

## Der Status ist der Kern

| Status | Bedeutung |
|---|---|
| `verified` | In der Trade-Republic-App gesehen |
| `assumed` | Aus einer Liste uebernommen, bei der eine hohe Trefferwahrscheinlichkeit besteht - Indexmitglieder, gaengige ETFs. **Nicht einzeln geprueft** |
| `unavailable` | Geprueft und nicht handelbar. Wird dauerhaft uebersprungen |
| `unknown` | Platzhalter |

Trade Republic bietet keine abfragbare Schnittstelle fuer die Handelbarkeit,
und ein automatisiertes Auslesen der App waere von deren Nutzungsbedingungen
nicht gedeckt. Der Statusansatz macht diese Unsicherheit sichtbar, statt eine
Gewissheit vorzuspiegeln, die die Datenlage nicht hergibt. In der Oberflaeche
steht der Status an jedem Treffer.

## Pflege im laufenden Betrieb

Der vorgesehene Weg ist **nicht** eine Pflegesitzung auf Vorrat, sondern:

1. Ein Titel taucht in einer Trefferliste auf.
2. Ein Klick auf den Namen oeffnet die Detailseite mit der ISIN zum Kopieren.
3. In der TR-App nach der ISIN suchen.
4. Zurueck in der Oberflaeche auf **Bei TR geprueft** oder **Nicht handelbar**.

Damit verbessert sich die Liste genau dort, wo sie tatsaechlich benutzt wird.
Die Aenderung landet in der Datenbank; ueber den Export laesst sie sich in die
CSV zurueckschreiben.

## Veraltete Pruefungen

Eintraege, deren Pruefung aelter als das eingestellte Intervall ist
(Vorgabe: 183 Tage), werden auf der Startseite und im Universum markiert.
Produkte verschwinden aus dem Handel; eine Liste ohne Verfallsdatum wird still
falsch.

## Liste erweitern

Zeile anhaengen und pruefen lassen:

```
trading-tool universe
```

Die Pruefung meldet mit Zeilennummer:

* ungueltige ISIN-Pruefziffer (faengt Tippfehler zuverlaessig),
* Dubletten,
* unbekannte Werte in `asset_class` oder `tr_status`,
* fehlende Yahoo-Ticker (Hinweis, kein Fehler - der Titel wird dann nur nicht
  gescreent).

Fehlerhafte Zeilen werden beim Laden uebersprungen, nicht geraten.

## Eigene Liste verwenden

Eine Datei `tr_universe.csv` im Datenverzeichnis
(`%LOCALAPPDATA%\TradingTool\`) hat Vorrang vor der mitgelieferten. So
ueberlebt eine eigene Liste jedes Update.

## Zum mitgelieferten Bestand

218 Eintraege: deutsche und europaeische Standardwerte, US-Schwergewichte,
gaengige UCITS-ETFs und vier Vergleichsindizes. Alle handelbaren Eintraege
stehen auf `assumed`.

**Die ISINs sind maschinell auf ihre Pruefziffer getestet, aber nicht
einzeln gegen ein Handelsregister verifiziert.** Vor einer Order gilt
ohnehin: in der TR-App nachsehen. Genau dafuer gibt es den Status.
