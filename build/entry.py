"""Startskript fuer den PyInstaller-Build.

PyInstaller fuehrt sein Einstiegsskript als ``__main__`` aus, nicht als Modul
innerhalb eines Pakets. Zeigt man es direkt auf ``trading_tool/__main__.py``,
scheitert dort jeder relative Import mit

    ImportError: attempted relative import with no known parent package

Deshalb dieser Umweg: ein Skript ohne eigene Logik, das das Paket absolut
importiert. Der Effekt laesst sich ohne PyInstaller nachstellen - siehe
tests/test_packaging.py.
"""

import sys

from trading_tool.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
