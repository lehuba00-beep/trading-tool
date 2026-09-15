@echo off
REM Start aus dem Quellcode heraus - fuer den Fall, dass Python installiert ist.
REM Wer keine Python-Installation hat, nimmt die fertige TradingTool.exe.
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Richte einmalig die Umgebung ein...
    python -m venv .venv || goto :kein_python
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -e .
)

.venv\Scripts\python.exe -m trading_tool serve
goto :ende

:kein_python
echo.
echo Python wurde nicht gefunden. Entweder Python 3.11 oder neuer von
echo python.org installieren - oder die fertige TradingTool.exe verwenden.
echo.
pause

:ende
endlocal
