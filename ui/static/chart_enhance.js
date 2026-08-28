/** Progressive chart enhancement on localhost — crosshair readout + drag zoom. */

(function () {
  var specEl = document.getElementById("chart-spec-json");
  if (!specEl) return;
  var spec;
  try {
    spec = JSON.parse(specEl.textContent);
  } catch (e) {
    return;
  }
  var svg = document.querySelector(".chart-wrap svg");
  if (!svg || !spec.dates || !spec.dates.length) return;

  var pad = spec.padding || 48;
  var w = spec.width;
  var h = spec.height;
  var n = spec.dates.length;
  var plotW = w - pad * 2;
  var plotH = h - pad * 2;
  var xStep = n > 1 ? plotW / (n - 1) : plotW;
  var ySpan = spec.y_max - spec.y_min || 1;

  var readout = document.createElement("div");
  readout.className = "meta-line";
  readout.style.marginTop = "0.25rem";
  readout.textContent = "Hover chart for crosshair";
  svg.parentNode.appendChild(readout);

  var vline = document.createElementNS("http://www.w3.org/2000/svg", "line");
  vline.setAttribute("stroke", "#6a7078");
  vline.setAttribute("stroke-dasharray", "3,3");
  vline.setAttribute("visibility", "hidden");
  svg.appendChild(vline);

  function idxFromX(clientX) {
    var rect = svg.getBoundingClientRect();
    var x = ((clientX - rect.left) / rect.width) * w;
    var rel = Math.max(0, Math.min(plotW, x - pad));
    return Math.round(rel / xStep);
  }

  svg.addEventListener("mousemove", function (ev) {
    var i = idxFromX(ev.clientX);
    if (i < 0 || i >= n) return;
    var xi = pad + i * xStep;
    vline.setAttribute("x1", xi);
    vline.setAttribute("x2", xi);
    vline.setAttribute("y1", pad);
    vline.setAttribute("y2", pad + plotH);
    vline.setAttribute("visibility", "visible");
    var close = spec.closes[i];
    var cb = spec.cost_basis && spec.cost_basis[i];
    readout.textContent = spec.dates[i] + " · close " + (close != null ? close.toFixed(2) : "—") +
      (cb != null ? " · avg cost " + cb.toFixed(2) : "");
  });

  svg.addEventListener("mouseleave", function () {
    vline.setAttribute("visibility", "hidden");
    readout.textContent = "Hover chart for crosshair";
  });

  var zoomStart = null;
  var overlay = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  overlay.setAttribute("fill", "rgba(57,135,229,0.15)");
  overlay.setAttribute("visibility", "hidden");
  svg.appendChild(overlay);

  svg.addEventListener("mousedown", function (ev) {
    zoomStart = idxFromX(ev.clientX);
  });
  svg.addEventListener("mouseup", function (ev) {
    if (zoomStart === null) return;
    var end = idxFromX(ev.clientX);
    overlay.setAttribute("visibility", "hidden");
    if (Math.abs(end - zoomStart) < 2) {
      zoomStart = null;
      return;
    }
    var i0 = Math.min(zoomStart, end);
    var i1 = Math.max(zoomStart, end);
    zoomStart = null;
    var x0 = pad + i0 * xStep;
    var x1 = pad + i1 * xStep;
    svg.setAttribute("viewBox", x0 + " 0 " + (x1 - x0) + " " + h);
  });
  svg.addEventListener("mousemove", function (ev) {
    if (zoomStart === null) return;
    var cur = idxFromX(ev.clientX);
    var i0 = Math.min(zoomStart, cur);
    var i1 = Math.max(zoomStart, cur);
    var x0 = pad + i0 * xStep;
    var x1 = pad + i1 * xStep;
    overlay.setAttribute("x", x0);
    overlay.setAttribute("y", pad);
    overlay.setAttribute("width", Math.max(1, x1 - x0));
    overlay.setAttribute("height", plotH);
    overlay.setAttribute("visibility", "visible");
  });
  svg.addEventListener("dblclick", function () {
    svg.removeAttribute("viewBox");
  });
})();
