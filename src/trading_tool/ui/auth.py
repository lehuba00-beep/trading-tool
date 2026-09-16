"""Passwortschutz fuer den Zugriff aus dem Netz.

Solange die Anwendung nur auf 127.0.0.1 hoert, braucht sie keine Anmeldung -
es kommt ohnehin niemand ausser dem eigenen Rechner dran. Sobald sie im WLAN
erreichbar ist, gilt das nicht mehr: Jedes Geraet im Netz koennte die
Watchlist lesen und Screenings ausloesen. Deshalb ist die Netzfreigabe ohne
gesetztes Passwort gesperrt, nicht bloss abgeraten.

Bewusst schlicht gehalten: ein Passwort, ein signiertes Sitzungsplaetzchen,
keine Benutzerverwaltung. Mehr braucht ein Werkzeug fuer einen Nutzer im
eigenen Heimnetz nicht - und weniger waere fahrlaessig.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path

log = logging.getLogger(__name__)

COOKIE_NAME = "tt_sitzung"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 Tage - das Handy soll sich merken lassen
PBKDF2_ITERATIONS = 240_000
SECRET_FILE = "session.key"

# Diese Pfade muessen ohne Anmeldung erreichbar sein, sonst laedt die
# Anmeldeseite ihr eigenes Stylesheet nicht.
# /ca.crt gehoert dazu: Ohne die Stelle kann das Handy die Verbindung gar
# nicht erst aufbauen, also auch nicht die Anmeldeseite laden.
OPEN_PATHS = ("/anmelden", "/static/", "/manifest.webmanifest", "/sw.js", "/icons/", "/ca.crt")


def hash_password(plain: str) -> str:
    """Passwort mit zufaelligem Salz ableiten. Klartext wird nie gespeichert."""
    salt = secrets.token_bytes(16)
    abgeleitet = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${abgeleitet.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    if not stored or not plain:
        return False
    try:
        verfahren, runden, salt_hex, erwartet_hex = stored.split("$")
        if verfahren != "pbkdf2_sha256":
            return False
        abgeleitet = hashlib.pbkdf2_hmac(
            "sha256", plain.encode(), bytes.fromhex(salt_hex), int(runden)
        )
    except (ValueError, TypeError):
        return False
    # Zeitkonstanter Vergleich: Ein gewoehnlicher Vergleich verraet ueber die
    # Laufzeit, wie viele Stellen bereits stimmen.
    return hmac.compare_digest(abgeleitet.hex(), erwartet_hex)


def load_or_create_secret(data_dir: Path) -> bytes:
    """Schluessel zum Signieren der Sitzung. Bleibt ueber Neustarts gleich,
    sonst waere man nach jedem Start wieder abgemeldet."""
    pfad = data_dir / SECRET_FILE
    if pfad.exists():
        # Ausdruecklich ohne strip(): Der Schluessel ist Binaerdaten, und rund
        # jedes zwanzigste Zufallsbyte am Rand ist zufaellig ein Zeichen, das
        # strip() entfernt. Der gelesene Schluessel waere dann ein anderer als
        # der geschriebene - und alle Sitzungen nach einem Neustart ungueltig.
        roh = pfad.read_bytes()
        if len(roh) >= 32:
            return roh

    schluessel = secrets.token_bytes(48)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(schluessel)
    # Windows kennt die Rechte so nicht - dort ist das folgenlos.
    with contextlib.suppress(OSError):
        os.chmod(pfad, 0o600)
    return schluessel


def _b64(roh: bytes) -> str:
    return base64.urlsafe_b64encode(roh).decode().rstrip("=")


def issue_token(secret: bytes, jetzt: float | None = None) -> str:
    """Signiertes Plaetzchen mit Ablaufzeitpunkt."""
    ablauf = int((jetzt or time.time()) + SESSION_MAX_AGE)
    nutzlast = f"{ablauf}".encode()
    signatur = hmac.new(secret, nutzlast, hashlib.sha256).digest()
    return f"{_b64(nutzlast)}.{_b64(signatur)}"


def token_valid(token: str, secret: bytes, jetzt: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    nutzlast_b64, _, signatur_b64 = token.partition(".")
    try:
        nutzlast = base64.urlsafe_b64decode(nutzlast_b64 + "=" * (-len(nutzlast_b64) % 4))
        signatur = base64.urlsafe_b64decode(signatur_b64 + "=" * (-len(signatur_b64) % 4))
    except (ValueError, TypeError):
        return False

    erwartet = hmac.new(secret, nutzlast, hashlib.sha256).digest()
    if not hmac.compare_digest(signatur, erwartet):
        return False
    try:
        ablauf = int(nutzlast.decode())
    except (ValueError, UnicodeDecodeError):
        return False
    return (jetzt or time.time()) < ablauf


def is_open_path(pfad: str) -> bool:
    return any(pfad == p or pfad.startswith(p) for p in OPEN_PATHS)


def lan_ready(settings) -> tuple[bool, str]:
    """Darf die Anwendung im Netz lauschen?

    Ohne Passwort ist die Antwort nein - und zwar als Sperre, nicht als
    Hinweis. Ein Werkzeug, das die eigene Watchlist ungeschuetzt ins WLAN
    stellt, ist ein Fehler, kein Komfortmerkmal.
    """
    if not settings.ui.allow_lan:
        return True, ""
    if not settings.ui.password_hash:
        return False, (
            "Zugriff aus dem Netz ist eingeschaltet, aber kein Passwort gesetzt.\n"
            "  Passwort setzen mit:  TradingTool.exe passwort\n"
            "  Oder die Netzfreigabe abschalten: ui.allow_lan: false in settings.yaml"
        )
    return True, ""


def bind_host(settings) -> str:
    return "0.0.0.0" if settings.ui.allow_lan else settings.ui.host  # noqa: S104


def tls_active(settings) -> bool:
    """Verschluesselung nur dort, wo sie etwas bewirkt.

    Auf 127.0.0.1 verlaesst kein Paket den Rechner - dort brächte TLS keinen
    Schutz, nur eine Zertifikatswarnung im Browser.
    """
    return bool(settings.ui.allow_lan and settings.ui.use_tls)


class LoginThrottle:
    """Bremse gegen das Durchprobieren von Passwoertern.

    Kein Heimnetz ist so klein, dass sich unbegrenzte Rateversuche lohnen
    wuerden. Nach jedem Fehlversuch wird die Antwort langsamer; das macht
    systematisches Probieren unbrauchbar, ohne den Nutzer auszusperren.
    """

    def __init__(self, max_delay: float = 5.0) -> None:
        self.fehlversuche = 0
        self.max_delay = max_delay

    @property
    def delay(self) -> float:
        return min(self.max_delay, 0.25 * (2 ** min(self.fehlversuche, 5)) - 0.25)

    def failed(self) -> float:
        self.fehlversuche += 1
        return self.delay

    def succeeded(self) -> None:
        self.fehlversuche = 0
