/* Service Worker.

   Zweck: Icon auf dem Startbildschirm, Vollbild ohne Browserleiste, und die
   zuletzt gesehenen Seiten bleiben lesbar, wenn das Netz weg ist.

   Die entscheidende Regel steht in NIEMALS_ZWISCHENSPEICHERN: Kurse,
   Auftragsstatus und Anmeldung duerfen nie aus dem Speicher kommen. Ein
   zwischengespeicherter Kurs waere schlimmer als gar keiner - er sieht
   aktuell aus und ist es nicht. */

const VERSION = "tt-v2";
const STATISCH = VERSION + "-statisch";
const SEITEN = VERSION + "-seiten";

const VORLADEN = [
  "/static/app.css",
  "/static/poll.js",
  "/icons/icon-192.png",
  "/manifest.webmanifest",
];

/* Alles, was immer frisch sein muss. */
const NIEMALS_ZWISCHENSPEICHERN = ["/kurse", "/jobs/status", "/anmelden", "/abmelden", "/export/"];

self.addEventListener("install", (ereignis) => {
  ereignis.waitUntil(
    caches.open(STATISCH).then((speicher) => speicher.addAll(VORLADEN)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (ereignis) => {
  ereignis.waitUntil(
    caches.keys().then((namen) =>
      Promise.all(
        namen.filter((n) => !n.startsWith(VERSION)).map((n) => caches.delete(n))
      )
    ).then(() => self.clients.claim())
  );
});

function istStatisch(pfad) {
  return pfad.startsWith("/static/") || pfad.startsWith("/icons/") || pfad === "/manifest.webmanifest";
}

function ausgenommen(pfad) {
  return NIEMALS_ZWISCHENSPEICHERN.some((p) => pfad === p || pfad.startsWith(p));
}

self.addEventListener("fetch", (ereignis) => {
  const anfrage = ereignis.request;
  if (anfrage.method !== "GET") return;

  const adresse = new URL(anfrage.url);
  if (adresse.origin !== self.location.origin) return;
  if (ausgenommen(adresse.pathname)) return;

  /* Statische Dateien: erst Speicher, dann Netz. Sie aendern sich nur mit
     einer neuen Programmfassung, und die bringt eine neue Speicherfassung mit. */
  if (istStatisch(adresse.pathname)) {
    ereignis.respondWith(
      caches.match(anfrage).then((treffer) => treffer || fetch(anfrage).then((antwort) => {
        if (antwort.ok) {
          const kopie = antwort.clone();
          caches.open(STATISCH).then((speicher) => speicher.put(anfrage, kopie));
        }
        return antwort;
      }))
    );
    return;
  }

  /* Seiten: erst Netz, bei Ausfall die zuletzt gesehene Fassung. So sind die
     Daten immer aktuell, solange es geht - und lesbar, wenn nicht. */
  ereignis.respondWith(
    fetch(anfrage)
      .then((antwort) => {
        /* Weiterleitungen und Fehlerseiten nicht ablegen: Sonst haengt man
           spaeter an einer zwischengespeicherten Anmeldeseite fest. */
        if (antwort.ok && antwort.type === "basic") {
          const kopie = antwort.clone();
          caches.open(SEITEN).then((speicher) => speicher.put(anfrage, kopie));
        }
        return antwort;
      })
      .catch(() =>
        caches.match(anfrage).then((treffer) => treffer || caches.match("/") ||
          new Response(
            "<!DOCTYPE html><html lang=de><meta charset=utf-8>" +
            "<meta name=viewport content='width=device-width,initial-scale=1'>" +
            "<title>Offline</title><link rel=stylesheet href=/static/app.css>" +
            "<main style='padding:24px'><h1>Keine Verbindung</h1>" +
            "<p class=muted>Das Trading-Tool ist gerade nicht erreichbar. " +
            "Läuft die Anwendung auf dem Rechner noch, und ist das Handy im " +
            "selben WLAN?</p></main>",
            { headers: { "Content-Type": "text/html; charset=utf-8" } }
          )
        )
      )
  );
});
