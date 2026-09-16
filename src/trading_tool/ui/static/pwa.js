/* Service Worker anmelden.

   Bleibt folgenlos, wo es ihn nicht gibt: Browser ohne Unterstuetzung und
   unsichere Herkuenfte ueberspringen den Aufruf einfach. */
(function () {
  "use strict";
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {
      /* Ohne Service Worker laeuft die Anwendung als gewoehnliche Webseite
         weiter - kein Grund, den Nutzer damit zu behelligen. */
    });
  });
})();
