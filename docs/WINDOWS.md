# Installation und Betrieb unter Windows

## Die fertige Anwendung beziehen

Auf dem Zielrechner ist kein Python installiert - deshalb wird eine
eigenstaendige `.exe` gebaut. **PyInstaller kann nicht plattformuebergreifend
bauen**: Eine Windows-Exe entsteht nur auf einem Windows-System. Der Bau laeuft
deshalb in GitHub Actions auf einem Windows-Runner.

Jeder Lauf prueft vorher, dass die gebaute Exe tatsaechlich startet - die
Kommandozeile und die Oberflaeche einzeln. Ein Artefakt, das dort liegt, ist
also nicht nur gebaut, sondern nachweislich lauffaehig.

1. Im Repository auf **Actions** gehen.
2. Den letzten erfolgreichen Lauf von **Windows-Build** oeffnen.
3. Unten unter **Artifacts** `TradingTool-windows` herunterladen.
4. Das ZIP an einen beliebigen Ort entpacken, zum Beispiel
   `C:\Programme\TradingTool` oder auf den Desktop.
5. `TradingTool.exe` starten.

Beim Start oeffnet sich ein Konsolenfenster mit der Adresse der Oberflaeche
(etwa `http://127.0.0.1:52341`) und kurz darauf der Browser. Das Konsolenfenster
bleibt offen, solange die Anwendung laeuft; Schliessen beendet sie.

### SmartScheen-Hinweis beim ersten Start

Die Datei ist nicht signiert. Windows zeigt deshalb beim ersten Start
*"Der Computer wurde durch Windows geschuetzt"*. Ueber **Weitere Informationen
&rarr; Trotzdem ausfuehren** starten. Eine Codesignatur waere kostenpflichtig
und fuer ein privat genutztes Werkzeug unverhaeltnismaessig.

## Wo die Daten liegen

Alles, was sich zur Laufzeit aendert, liegt unter

    %LOCALAPPDATA%\TradingTool\

| Datei | Inhalt |
|---|---|
| `cache.sqlite` | Kurse, Watchlist, Laeufe, Signale |
| `settings.yaml` | Einstellungen (wird beim ersten Start angelegt) |
| `trading-tool.log` | Protokoll |
| `exports\` | CSV- und Excel-Ausgaben |
| `strategies\` | eigene Strategieprofile (haben Vorrang vor den mitgelieferten) |
| `tr_universe.csv` | eigene Universumsliste (hat Vorrang vor der mitgelieferten) |

Das Programmverzeichnis bleibt unangetastet. Ein Update besteht darin, den
Ordner zu ersetzen - die Daten bleiben erhalten.

## Betrieb

* **Erster Start:** Die Kurshistorie ist leer. Der erste Screening-Lauf laedt
  rund vier Jahre Tagesbalken fuer gut 200 Titel und dauert je nach Verbindung
  **einige Minuten**. Danach werden nur noch die fehlenden Tage nachgeladen,
  ein Lauf dauert dann unter einer Minute.
* **Zeitsteuerung:** Dreimal taeglich um 09:30, 14:00 und 22:30 (werktags),
  aenderbar in `settings.yaml`. Die Anwendung muss dafuer laufen - sie startet
  sich nicht selbst.
* **Autostart:** Wer das moechte, legt eine Verknuepfung auf `TradingTool.exe`
  in den Ordner, den `shell:startup` im Ausfuehren-Dialog oeffnet.
* **Beenden:** Konsolenfenster schliessen oder Strg+C.

## Ohne Oberflaeche

Die Exe versteht auch Unterbefehle - nuetzlich zur Kontrolle beim Einrichten:

```
TradingTool.exe universe        Universumsliste pruefen
TradingTool.exe rules           verfuegbare Regelbausteine auflisten
TradingTool.exe screen -s swing Screening ohne Oberflaeche
TradingTool.exe backtest -s swing
```

## Aus dem Quellcode starten

Falls doch Python 3.11 oder neuer installiert ist, genuegt `start_windows.bat`.
Das Skript legt beim ersten Aufruf eine virtuelle Umgebung an und startet die
Anwendung.

## Wenn etwas nicht laeuft

| Symptom | Ursache und Abhilfe |
|---|---|
| Browser oeffnet sich nicht | Die Adresse aus dem Konsolenfenster von Hand aufrufen. |
| Keine Treffer in allen Profilen | Noch keine Kurse geladen - erst ein Screening laufen lassen. Die Pflichtfilter sind zudem bewusst streng. |
| "keine Quelle" im Protokoll | Yahoo drosselt oder hat das Format geaendert. Stooq springt automatisch ein; ansonsten spaeter erneut versuchen. |
| Zeitsteuerung feuert nicht | Die Anwendung muss laufen. Naechste Termine stehen unter Einstellungen. |
| Firewall fragt nach | Die Anwendung bindet nur auf `127.0.0.1` und ist von aussen nicht erreichbar. Eine Freigabe ist nicht noetig. |
