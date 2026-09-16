"""Transportverschluesselung fuer den Zugriff aus dem Heimnetz.

Ohne HTTPS gehen Passwort und Daten im Klartext durchs WLAN. Das laesst sich
beheben - aber es ist wichtig, zu wissen, *was* damit behoben ist:

* **Behoben:** Mitlesen und Veraendern auf dem Uebertragungsweg. Wer im selben
  Netz lauscht, sieht nur noch verschluesselten Verkehr.
* **Nicht behoben:** Erreichbarkeit. Eine Portfreigabe im Router setzt die
  Anwendung weiterhin dem gesamten Internet aus - dann eben verschluesselt.
  Verschluesselung ersetzt kein VPN, sie ergaenzt es.

Aufbau: eine eigene kleine Zertifizierungsstelle und ein davon signiertes
Serverzertifikat. Der Umweg lohnt sich, weil die Stelle **einmal** auf dem
Handy hinterlegt wird und danach dauerhaft vertraut wird - auch wenn der
Rechner eine neue Adresse bekommt und das Serverzertifikat neu ausgestellt
werden muss. Bei einem einzelnen selbstsignierten Zertifikat waere jedes Mal
wieder eine Warnung faellig.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import ipaddress
import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

TLS_DIR = "tls"
CA_KEY = "ca.key"
CA_CERT = "ca.crt"
SERVER_KEY = "server.key"
SERVER_CERT = "server.crt"

CA_YEARS = 10
# Browser lehnen sehr lange Laufzeiten ab; 397 Tage sind die gaengige
# Obergrenze fuer Serverzertifikate.
SERVER_DAYS = 397
RENEW_BEFORE_DAYS = 30


@dataclass(slots=True)
class Certificate:
    ca_cert: Path
    server_cert: Path
    server_key: Path

    @property
    def complete(self) -> bool:
        return all(p.exists() for p in (self.ca_cert, self.server_cert, self.server_key))


def tls_dir(data_dir: Path) -> Path:
    return data_dir / TLS_DIR


def paths(data_dir: Path) -> Certificate:
    verzeichnis = tls_dir(data_dir)
    return Certificate(
        ca_cert=verzeichnis / CA_CERT,
        server_cert=verzeichnis / SERVER_CERT,
        server_key=verzeichnis / SERVER_KEY,
    )


def local_addresses() -> tuple[list[str], list[str]]:
    """(Namen, Adressen), die das Zertifikat abdecken muss."""
    namen = {"localhost"}
    adressen = {"127.0.0.1", "::1"}

    rechner = socket.gethostname()
    if rechner:
        namen.add(rechner)
        namen.add(f"{rechner}.local")  # Bonjour/mDNS im Heimnetz

    # Die nach aussen gerichtete Adresse ueber eine Testroute ermitteln -
    # es werden dabei keine Daten gesendet.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        adressen.add(str(probe.getsockname()[0]))
    except OSError:
        pass
    finally:
        probe.close()

    try:
        for eintrag in socket.getaddrinfo(rechner, None, socket.AF_INET):
            adressen.add(eintrag[4][0])
    except (socket.gaierror, OSError):
        pass

    return sorted(namen), sorted(adressen)


def _write_private(pfad: Path, inhalt: bytes) -> None:
    """Privaten Schluessel ablegen und, wo moeglich, die Rechte einschraenken."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(inhalt)
    # Windows kennt die Rechte so nicht - dort ist das folgenlos.
    with contextlib.suppress(OSError):
        os.chmod(pfad, 0o600)


def certificate_covers(cert_path: Path, namen: list[str], adressen: list[str]) -> bool:
    """Deckt das vorhandene Zertifikat die aktuellen Adressen noch ab?

    Wichtig bei wechselnder Adresse aus dem Router: Ein Zertifikat fuer die
    alte Adresse wuerde im Browser eine Warnung ausloesen, obwohl alles
    eingerichtet ist.
    """
    from cryptography import x509

    if not cert_path.exists():
        return False
    try:
        zertifikat = x509.load_pem_x509_certificate(cert_path.read_bytes())
    except ValueError:
        return False

    if zertifikat.not_valid_after_utc <= dt.datetime.now(dt.UTC) + dt.timedelta(
        days=RENEW_BEFORE_DAYS
    ):
        return False

    try:
        san = zertifikat.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound:
        return False

    enthaltene_namen = set(san.get_values_for_type(x509.DNSName))
    enthaltene_ips = {str(a) for a in san.get_values_for_type(x509.IPAddress)}
    return set(namen) <= enthaltene_namen and set(adressen) <= enthaltene_ips


def _create_ca(ziel: Certificate) -> tuple:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    schluessel = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Trading-Tool Lokale Stelle"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Trading-Tool"),
    ])
    jetzt = dt.datetime.now(dt.UTC)
    zertifikat = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(jetzt - dt.timedelta(hours=1))
        .not_valid_after(jetzt + dt.timedelta(days=365 * CA_YEARS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(schluessel, hashes.SHA256())
    )

    _write_private(
        ziel.ca_cert.parent / CA_KEY,
        schluessel.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    ziel.ca_cert.write_bytes(zertifikat.public_bytes(serialization.Encoding.PEM))
    return schluessel, zertifikat


def _load_ca(ziel: Certificate) -> tuple:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    schluessel_pfad = ziel.ca_cert.parent / CA_KEY
    if not (ziel.ca_cert.exists() and schluessel_pfad.exists()):
        return _create_ca(ziel)
    try:
        schluessel = serialization.load_pem_private_key(schluessel_pfad.read_bytes(), None)
        zertifikat = x509.load_pem_x509_certificate(ziel.ca_cert.read_bytes())
    except ValueError:
        log.warning("Zertifizierungsstelle unlesbar - wird neu erzeugt")
        return _create_ca(ziel)
    return schluessel, zertifikat


def ensure_certificate(data_dir: Path, force: bool = False) -> Certificate:
    """Serverzertifikat bereitstellen, bei Bedarf neu ausstellen.

    Die Zertifizierungsstelle bleibt dabei erhalten - nur so behaelt ein
    einmal auf dem Handy hinterlegtes Vertrauen seine Gueltigkeit.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    ziel = paths(data_dir)
    tls_dir(data_dir).mkdir(parents=True, exist_ok=True)
    namen, adressen = local_addresses()

    if not force and ziel.complete and certificate_covers(ziel.server_cert, namen, adressen):
        return ziel

    ca_schluessel, ca_zertifikat = _load_ca(ziel)
    schluessel = ec.generate_private_key(ec.SECP256R1())

    eintraege: list = [x509.DNSName(n) for n in namen]
    for adresse in adressen:
        try:
            eintraege.append(x509.IPAddress(ipaddress.ip_address(adresse)))
        except ValueError:
            continue

    jetzt = dt.datetime.now(dt.UTC)
    zertifikat = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Trading-Tool")]))
        .issuer_name(ca_zertifikat.subject)
        .public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(jetzt - dt.timedelta(hours=1))
        .not_valid_after(jetzt + dt.timedelta(days=SERVER_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        # Browser ignorieren den Common Name seit Jahren - allein diese Liste
        # entscheidet, fuer welche Adressen das Zertifikat gilt.
        .add_extension(x509.SubjectAlternativeName(eintraege), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_schluessel, hashes.SHA256())
    )

    _write_private(
        ziel.server_key,
        schluessel.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    ziel.server_cert.write_bytes(zertifikat.public_bytes(serialization.Encoding.PEM))
    log.info("Zertifikat ausgestellt fuer %s / %s", ", ".join(namen), ", ".join(adressen))
    return ziel
