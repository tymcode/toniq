(function () {
  "use strict";

  var input = document.getElementById("delay-tempo-bpm-input");
  if (!input) {
    return;
  }

  var cells = document.querySelectorAll(".delay-tempo-calc-results .delay-ms");

  function formatMs(ms) {
    return ms.toFixed(2);
  }

  function update() {
    var bpm = Number(input.value);
    if (!Number.isFinite(bpm) || bpm <= 0) {
      cells.forEach(function (cell) {
        cell.textContent = "—";
      });
      return;
    }
    cells.forEach(function (cell) {
      var numerator = Number(cell.dataset.numerator);
      cell.textContent = formatMs(numerator / bpm);
    });
  }

  input.addEventListener("input", update);
  input.addEventListener("change", update);
  update();
})();
