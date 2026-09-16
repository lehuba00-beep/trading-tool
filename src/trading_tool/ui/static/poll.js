/* Minimaler Ersatz fuer die eine Sache, die hier Javascript braucht:
   ein Element regelmaessig nachladen. Eine vollstaendige Bibliothek waere
   fuer diesen einen Zweck unverhaeltnismaessig - und muesste mitgeliefert
   werden, damit die App offline funktioniert. */
(function () {
  "use strict";

  function refresh(element) {
    var url = element.getAttribute("hx-get");
    if (!url) return;
    fetch(url, { headers: { "X-Requested-With": "poll" } })
      .then(function (response) {
        return response.ok ? response.text() : null;
      })
      .then(function (html) {
        if (html !== null) element.innerHTML = html;
      })
      .catch(function () {
        /* Ein fehlgeschlagener Abruf darf die Seite nicht stoeren -
           beim naechsten Intervall wird es erneut versucht. */
      });
  }

  function parseInterval(trigger) {
    var match = /every\s+(\d+)(m?s)/.exec(trigger || "");
    if (!match) return 0;
    var value = parseInt(match[1], 10);
    return match[2] === "ms" ? value : value * 1000;
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[hx-get]").forEach(function (element) {
      var trigger = element.getAttribute("hx-trigger") || "";
      if (trigger.indexOf("load") !== -1) refresh(element);
      var interval = parseInterval(trigger);
      if (interval > 0) setInterval(function () { refresh(element); }, interval);
    });
  });
})();

/* Laufend aktualisierte Kurse.

   Keine Echtzeitkurse - die Quelle liefert verzoegert. Deshalb wird neben dem
   Kurs immer der Abrufzeitpunkt angezeigt; ein Kurs ohne Zeitstempel waere
   eine stille Behauptung von Aktualitaet. */
(function () {
  "use strict";

  function zellen() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-kurs]"));
  }

  function formatiere(zahl, stellen) {
    return zahl.toLocaleString("de-DE", {
      minimumFractionDigits: stellen,
      maximumFractionDigits: stellen,
    });
  }

  function schreibe(zelle, eintrag) {
    var wert = zelle.querySelector(".kurs-wert");
    if (wert) wert.textContent = formatiere(eintrag.preis, 2);

    var delta = zelle.querySelector(".kurs-delta");
    if (!delta) return;
    if (eintrag.veraenderung === null || eintrag.veraenderung === undefined) {
      delta.textContent = "";
      return;
    }
    var vorzeichen = eintrag.veraenderung > 0 ? "+" : "";
    delta.textContent = vorzeichen + formatiere(eintrag.veraenderung, 2) + " %";
    delta.className = "kurs-delta " + (eintrag.veraenderung >= 0 ? "pos" : "neg");
  }

  function aktualisiereStand(daten) {
    var anzeige = document.getElementById("kurs-stand");
    if (!anzeige) return;
    if (daten.fehler) {
      anzeige.textContent = "Kurse nicht abrufbar - angezeigt sind Schlusskurse";
      anzeige.className = "kurs-stand fehler";
      return;
    }
    if (!daten.abgerufen) return;
    anzeige.textContent = "Kurse abgerufen " + daten.abgerufen + " · verzögert";
    anzeige.className = "kurs-stand";
  }

  function hole() {
    var liste = zellen();
    if (!liste.length) return;

    var isins = liste.map(function (zelle) {
      return zelle.getAttribute("data-kurs");
    });

    fetch("/kurse?isins=" + encodeURIComponent(isins.join(",")))
      .then(function (antwort) {
        return antwort.ok ? antwort.json() : null;
      })
      .then(function (daten) {
        if (!daten) return;
        liste.forEach(function (zelle) {
          var eintrag = daten.kurse[zelle.getAttribute("data-kurs")];
          if (eintrag) schreibe(zelle, eintrag);
        });
        aktualisiereStand(daten);
      })
      .catch(function () {
        /* Ein fehlgeschlagener Abruf laesst die Schlusskurse stehen. */
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!zellen().length) return;
    var intervall = parseInt(document.body.getAttribute("data-kurs-intervall"), 10);
    if (!intervall || intervall < 5) return;
    hole();
    setInterval(hole, intervall * 1000);
  });
})();
