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
