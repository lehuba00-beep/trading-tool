# Datenquellen

## 1. Kursdaten für Aktien und ETFs

Vorab die wichtigste Entlastung: **Für Signale über 1–5 Tage genügen
Tagesschlusskurse.** Ein Setup, das auf 1-Minuten-Daten angewiesen ist, ist kein
Swing-Trading-Setup mehr, sondern Daytrading – mit anderen Anforderungen an
Latenz, Spread und Kosten. Realtime-Daten sind also kein Muss, sondern
Komfort (Intraday-Vorabprüfung eines am Vorabend erzeugten Signals).

| Quelle | Kosten | Abdeckung DE/EU | Granularität | Bewertung |
|---|---|---|---|---|
| **yfinance** (Yahoo, inoffiziell) | 0 € | gut: Xetra `.DE`, Frankfurt `.F`, Stuttgart `.SG`, ETFs, US | EOD + Intraday (verzögert, 60 Tage Historie bei 1m) | Bequem, breite Abdeckung, viele Metadaten. Inoffizielle Schnittstelle: bricht erfahrungsgemäß mehrmals pro Jahr, Rate-Limits undokumentiert, Nutzung außerhalb der Yahoo-Nutzungsbedingungen. Für private Analyse pragmatisch, als alleinige Basis riskant |
| **Stooq** (CSV) | 0 € | deutsche Titel (`sap.de`), Indizes, US | nur EOD | Sehr stabil, kein Key, kein Rate-Limit-Drama. Dünne Metadaten, keine ISIN-Zuordnung, Volumendaten teils lückenhaft. Ideal als **Fallback und Plausibilitäts-Kreuzcheck** |
| **Alpha Vantage** | Free stark limitiert (Größenordnung einige Dutzend Abrufe/Tag – bitte aktuell prüfen), Premium ab ca. 50 $/Monat | schwach für EU | EOD + Intraday | Free-Tier reicht für ein Screening über >50 Titel nicht |
| **Twelve Data** | Free ca. 800 Credits/Tag, 8/min; Bezahltarife ab ca. 10–30 $/Monat | ordentlich, ISIN-Suche in Bezahltarifen | EOD + Intraday | Brauchbarer Mittelweg, wenn yfinance zu unzuverlässig wird |
| **EODHD** | ab ca. 20–30 €/Monat | sehr gut, inkl. **ISIN→Ticker-Mapping** und europäischer Börsen | EOD + Intraday | Löst das ISIN-Problem am saubersten; die Option, wenn das Tool dauerhaft genutzt wird |
| Börsen-/Emittentenseiten (onvista, ariva, finanzen.net, justETF) | 0 € | sehr gut | EOD | Scraping ist durch die jeweiligen Nutzungsbedingungen regelmäßig untersagt und technisch brüchig. **Nicht als Architekturbaustein vorgesehen**; punktuell als manuell ausgelöster Import durch den Nutzer denkbar |

**Empfehlung:** Start mit yfinance als Primärquelle, Stooq als Fallback und
CSV-Import als letzter Rückfallweg. Die Provider-Abstraktion ist so geschnitten,
dass ein Wechsel auf EODHD/Twelve Data später eine Datei betrifft. Wenn absehbar
ist, dass das Tool dauerhaft läuft, spricht viel dafür, gleich einen bezahlten
Anbieter mit ISIN-Mapping zu nehmen – das erspart den größten Teil der
Symbol-Pflege (s. Abschnitt 2).

### Bekannte Fallstricke, die eingeplant werden

* **ISIN ↔ Ticker.** Die Trade-Republic-Welt denkt in ISINs, die Kursquellen in
  Tickern. Ohne bezahltes Mapping muss die Zuordnung in der Universum-CSV
  gepflegt werden; sie ist der eigentliche Wartungsaufwand des Projekts.
* **Handelsplatz-Divergenz.** Trade Republic führt Orders außerbörslich bzw.
  über den angebundenen Handelsplatz aus; die Analyse läuft auf Xetra-/
  Heimatbörsendaten. Für Signale unerheblich, für Einstiegskurse nicht – in der
  UI wird darum kein Kurs als „TR-Kurs“ ausgewiesen, sondern Quelle und
  Handelsplatz benannt.
* **Währung.** US-Titel werden bei TR in EUR abgerechnet, die Kursdaten kommen
  in USD. Über mehrere Monate verschiebt der Wechselkurs die tatsächliche
  Performance spürbar. Offener Punkt: EUR-Umrechnung ja/nein (s. OPEN_QUESTIONS).
* **Dividenden/Splits.** Indikatoren auf bereinigten Reihen, Kursniveaus und
  Stops auf Rohkursen – sonst erzeugt jeder Split ein Scheinsignal.
* **Handelsfreie Tage.** Deutsche und US-Feiertage unterscheiden sich; Lücken
  dürfen nicht als Kursbewegung interpretiert werden.

## 2. Handelbarkeit bei Trade Republic

Es gibt keine öffentliche, für Dritte nutzbare Schnittstelle, die die
Handelbarkeit abfragbar macht. Automatisiertes Auslesen der TR-App oder
-Website wäre zudem von deren Nutzungsbedingungen nicht gedeckt und technisch
instabil. Vorgeschlagen wird deshalb eine **kuratierte, versionierte Liste** im
Repository.

### Format `universe/tr_universe.csv`

```csv
isin,name,asset_class,ticker_yahoo,ticker_stooq,currency,exchange,tr_status,tr_checked_at,source,notes
DE0007164600,SAP SE,stock,SAP.DE,sap.de,EUR,XETRA,verified,2026-09-10,dax40,
IE00B4L5Y983,iShares Core MSCI World,etf,EUNL.DE,,EUR,XETRA,verified,2026-09-10,tr_etf_list,Sparplan
US0378331005,Apple Inc.,stock,AAPL,aapl.us,USD,NASDAQ,assumed,2026-09-10,nasdaq100,Abrechnung in EUR
```

`tr_status` ist der Kern des Ansatzes:

| Status | Bedeutung |
|---|---|
| `verified` | manuell in der TR-App gesehen |
| `assumed` | aus einer Quelle übernommen, bei der eine hohe Trefferwahrscheinlichkeit besteht (Indexmitglieder, TR-ETF-Liste), aber nicht einzeln geprüft |
| `unavailable` | geprüft und nicht handelbar → dauerhaft aus dem Screening |
| `unknown` | Platzhalter |

In der UI wird der Status an jedem Treffer angezeigt, und es lässt sich
einstellen, ob `assumed` mitgescreent wird. So bleibt die Anforderung
„nur bei TR handelbar“ erfüllt, ohne dass zum Start tausende Titel einzeln
geprüft werden müssen – und ohne dem Nutzer eine Sicherheit vorzuspiegeln, die
die Datenlage nicht hergibt.

### Pflege-Workflow

1. **Seed (einmalig, automatisierbar):** Indexkonstituenten von DAX, MDAX,
   SDAX, TecDAX, EURO STOXX 50, S&P 500 und Nasdaq-100 als `assumed`. Diese
   Titel sind bei TR nahezu vollständig handelbar und decken den für
   kurzfristiges Trading relevanten liquiden Teil des Marktes weitgehend ab.
2. **ETFs:** Trade Republic veröffentlicht seine sparplanfähigen ETFs; die Liste
   lässt sich als Ausgangsbasis übernehmen (Größenordnung mehrere tausend
   Positionen). Sinnvoll ist eine Reduktion auf die liquiden Standard-ETFs.
3. **Verifikation im Betrieb:** Jeder Treffer bekommt in der UI einen Button
   „Bei TR geprüft“, der `tr_status` auf `verified` und `tr_checked_at` auf heute
   setzt. Die Liste verbessert sich dadurch genau dort, wo sie benutzt wird,
   statt in einer Pflegesitzung auf Vorrat.
4. **Manueller Import:** Ein Nutzer-Export (z. B. eine eigene Watchlist als CSV)
   kann eingelesen und gemerged werden – Merge nach ISIN, bestehende
   `verified`-Einträge gewinnen.
5. **Veraltungswarnung:** Einträge mit `tr_checked_at` älter als n Monate
   (Vorschlag: 6) werden in der UI markiert. Produkte verschwinden aus dem
   Handel; eine Liste ohne Verfallsdatum wird still falsch.
6. **Versionierung:** Die CSV liegt im Git. Jede Änderung ist nachvollziehbar
   und rücknehmbar; das ist der billigste verfügbare Audit-Trail.

## 3. Derivate (Knock-Outs, Optionsscheine, Faktor-Zertifikate)

### Ausgangslage

* In Deutschland sind mehrere hunderttausend bis über eine Million
  Hebelprodukte notiert. Die Kurse stellt der Emittent, nicht ein Orderbuch.
* Standard-Kurs-APIs decken diese Produkte praktisch nicht ab.
* Die Emittenten (HSBC, Vontobel, Société Générale, Morgan Stanley, BNP, UniCredit,
  DZ Bank) betreiben Produktfinder im Web; teils mit CSV-/Excel-Export.
  Dokumentierte, frei nutzbare APIs sind die Ausnahme – wo es sie gibt, laufen
  sie in der Regel über eine Partner-/Vertriebsvereinbarung. Scraping der
  Produktfinder ist von den Nutzungsbedingungen meist nicht gedeckt.
* Selbst mit Daten bliebe das Matching aufwändig: Basiswert, Typ, Basispreis,
  Knock-Out-Schwelle, Bezugsverhältnis, Laufzeit, Spread und Emittentenrisiko
  müssten je Produkt geführt werden.

### Empfehlung: Zweistufig

**Stufe 1 (v1) – Signale auf dem Basiswert, Derivat als Umsetzung.**
Das Tool screent Aktien/ETFs/Indizes und liefert zu jedem Treffer eine
Derivate-Umsetzungshilfe, die ohne jede Produktdatenbank auskommt:

* Richtung (Long/Short → Call/Put bzw. Long-/Short-KO),
* aus der Volatilität abgeleiteter **maximal sinnvoller Hebel** und
  **Mindestabstand der Knock-Out-Schwelle** (Rechenweg in SIGNALS.md),
* Hinweis auf Produkttyp-Eignung je Haltedauer (Faktor-Zertifikate nur bei
  klarem Trend und kurzer Haltedauer – der tägliche Reset frisst in
  Seitwärtsphasen Substanz),
* Deeplink in den Produktfinder des jeweiligen Emittenten, vorgefiltert auf
  Basiswert und Richtung, sowie in die TR-Suche zur ISIN.

Das deckt den Großteil des praktischen Nutzens ab: Die Handelsidee entsteht am
Basiswert, das Zertifikat ist nur das Vehikel. Die Produktauswahl trifft der
Nutzer dort, wo die Kurse ohnehin verbindlich stehen.

**Stufe 2 (später, optional) – Produktliste importieren.**
Wenn sich herausstellt, dass die Produktauswahl zu viel Handarbeit ist: ein
Importer für vom Nutzer heruntergeladene Emittenten-Exporte (CSV/XLSX).
Matching über Basiswert-ISIN + Typ + Barrierenband; das Tool schlägt dann aus
der importierten Liste passende Produkte vor. Nur Stammdaten, keine laufenden
Kurse – damit bleibt die Lösung rechtlich und technisch unkritisch. Ein echter
Live-Kursfeed für Hebelprodukte ist ohne kostenpflichtige Vereinbarung mit
einem Datenanbieter realistisch nicht zu haben.

## 4. Laufend aktualisierte Kurse

**Es sind keine Echtzeitkurse.** Yahoo liefert je nach Börse 15 bis 20 Minuten
verzögert. Echte Realtime-Daten setzen einen lizenzierten, kostenpflichtigen
Feed voraus — Börsen verkaufen Realtime-Berechtigungen einzeln, und kein
kostenloser Anbieter darf sie weitergeben. Wer Realtime braucht, kommt an einem
Bezahlabo nicht vorbei.

Was das Werkzeug stattdessen tut: Es holt in regelmäßigen Abständen den
aktuellsten verfügbaren Kurs und zeigt ihn **mit Abrufzeitpunkt und
Verzögerungshinweis** an. Ein Kurs, der so aussieht wie Realtime, aber keiner
ist, wäre gefährlicher als gar keiner.

Zwei Eigenschaften machen das alltagstauglich, ohne die Quelle zu überlasten:

* **Gebündelter Abruf.** Alle sichtbaren Titel werden in *einer* Anfrage geholt.
  Eine Trefferliste mit 50 Zeilen würde die Quelle sonst binnen Minuten drosseln.
* **Zwischenspeicher mit Verfallszeit** (Vorgabe 25 Sekunden, knapp unter dem
  Abfrageintervall von 30 Sekunden). Die Oberfläche darf häufiger fragen, als
  die Quelle verträgt.

Technisch werden Tagesbalken statt Minutendaten abgerufen: Der Balken des
laufenden Handelstages wird von Yahoo während der Sitzung fortgeschrieben und
liefert damit Kurs *und* Vortagesschluss für die Veränderung — in einer Abfrage
statt in zweien.

Scheitert der Abruf, bleiben die Schlusskurse stehen und die Statuszeile sagt
es. Ein fehlender Wechselkurs führt dazu, dass gar kein Live-Kurs angezeigt wird
statt eines falsch umgerechneten.

## 5. Termine für Quartalszahlen

Das Regelwerk kennt nur Kurse. Ein Ausbruchssignal zwei Tage vor Quartalszahlen
ist ein Münzwurf, den kein Indikator erkennen kann. Deshalb wird der nächste
Termin je Titel mitgeführt und gewarnt, wenn er in die geplante Haltedauer der
jeweiligen Strategie fällt.

Die Daten kommen aus derselben Quelle und sind **unvollständig**: Für ETFs und
Indizes gibt es keine Termine, für manche Nebenwerte auch nicht, und geschätzte
Termine verschieben sich. Sie sind ein Hinweis, keine Zusicherung — was sich
nicht zweifelsfrei in ein Datum übersetzen lässt, gilt als unbekannt. Ein falsch
geratener Termin wäre schlechter als gar keiner.

Abgefragt wird begrenzt (Vorgabe 40 Titel je Lauf, Auffrischung nach sieben
Tagen), weil jeder Termin ein eigener Abruf ist. Über mehrere Läufe ist die
Liste trotzdem schnell vollständig. Auch ein leeres Ergebnis wird vermerkt, sonst
fragt jeder Lauf erneut nach Titeln, für die die Quelle ohnehin nichts hat.

## 6. Datenqualität

Die kostenlosen Quellen liefern gelegentlich fehlerhafte Einzelkurse. Ein
falscher Ausreißer nach oben erzeugt ein makelloses Donchian-Ausbruchssignal —
der Screener kann nicht wissen, dass dieser Kurs nie gehandelt wurde. Ebenso
still ist eine Reihe, die vor drei Wochen aufgehört hat zu laufen: Alle
Indikatoren rechnen weiter, nur eben auf altem Stand.

Geprüft wird auf:

| Befund | Erkennung |
|---|---|
| **Veraltet** | Letzter Balken älter als fünf Handelstage |
| **Verdächtiger Kurssprung** | Sprung über 20 %, bei dem der Kurs am Folgetag wieder nahe am Ausgangsniveau liegt |
| **Widersprüchlicher Balken** | Hoch unter Tief, Schluss oder Eröffnung außerhalb der Tagesspanne |
| **Eingefrorene Reihe** | Zehn Tage oder mehr ohne Kursänderung |
| **Lücken** | Weniger als 85 % der Handelstage im Zeitraum vorhanden |
| **Fehlendes Volumen** | Volumen fehlt an über 30 % der letzten 60 Tage |

Zum Sprung-Kriterium: Verglichen wird das **Kursniveau vor und nach** dem
Balken, nicht die Summe der Tagesrenditen. Ein Sprung um +45 % und vollständig
zurück ergibt −31 %, in der Summe also +14 % — das ist Prozentarithmetik, kein
Restfehler. Wer darauf schwellt, übersieht genau die großen Ausreißer.

Titel mit Befund werden **markiert, nicht aussortiert**. Stilles Weglassen würde
genau die Information verbergen, um derentwillen geprüft wird.
