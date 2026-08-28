/** Desk console + routine launcher (vanilla JS, no CDN). */

(function () {
  var CONSOLE_KEY = "desk_console_log";
  var CONSOLE_MAX = 50000;

  function $(sel) { return document.querySelector(sel); }

  function persistConsole(text) {
    try {
      var prev = sessionStorage.getItem(CONSOLE_KEY) || "";
      var next = (prev + text).slice(-CONSOLE_MAX);
      sessionStorage.setItem(CONSOLE_KEY, next);
    } catch (e) {}
  }

  function restoreConsole() {
    var el = $("#console-output");
    if (!el) return;
    try {
      var saved = sessionStorage.getItem(CONSOLE_KEY);
      if (saved) {
        el.textContent = saved;
      }
    } catch (e) {}
  }

  function appendConsole(text) {
    var el = $("#console-output");
    if (!el) return;
    var dock = $("#console-dock");
    if (dock && !dock.open) dock.open = true;
    if (el.textContent.startsWith("(empty")) el.textContent = "";
    el.textContent += text + "\n";
    el.scrollTop = el.scrollHeight;
    persistConsole(text + "\n");
  }

  function collectArgs(card) {
    var args = {};
    card.querySelectorAll("input[name^='arg-']").forEach(function (inp) {
      var name = inp.name.replace(/^arg-/, "");
      if (inp.value.trim()) args[name] = inp.value.trim();
    });
    return args;
  }

  function formatElapsed(sec) {
    if (sec < 60) return sec + "s";
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return m + "m " + s + "s";
  }

  function streamRun(runId, card) {
    var elapsedEl = card ? card.querySelector(".elapsed") : null;
    var doneNote = card ? card.querySelector(".refresh-done") : null;
    var timerId = null;
    var started = Date.now();
    if (elapsedEl) {
      elapsedEl.hidden = false;
      timerId = setInterval(function () {
        var sec = Math.floor((Date.now() - started) / 1000);
        elapsedEl.textContent = "elapsed " + formatElapsed(sec);
      }, 1000);
    }
    var es = new EventSource("/run/" + runId + "/stream");
    es.onmessage = function (ev) {
      appendConsole(ev.data);
    };
    es.addEventListener("done", function (ev) {
      es.close();
      if (timerId) clearInterval(timerId);
      if (card) card.classList.remove("running");
      try {
        var payload = JSON.parse(ev.data);
        appendConsole("— exit " + payload.exit_code);
        if (payload.artifact_path) {
          appendConsole("artifact: " + payload.artifact_path);
        }
        if (doneNote) {
          doneNote.hidden = false;
          doneNote.textContent = "Refresh complete — reload to see the updated campaign.";
        }
      } catch (e) {}
    });
    es.onerror = function () {
      es.close();
      if (timerId) clearInterval(timerId);
      if (card) card.classList.remove("running");
    };
  }

  document.querySelectorAll(".launch-routine").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var card = btn.closest("[data-routine-id]");
      if (!card) return;
      var rid = card.getAttribute("data-routine-id");
      var needsConfirm = card.getAttribute("data-confirm-name") === "1";
      var confirmInput = card.querySelector("input[name='confirm-name']");
      var confirmName = confirmInput ? confirmInput.value.trim() : null;
      if (needsConfirm && confirmName !== rid) {
        appendConsole("refused: type " + rid + " exactly to confirm");
        return;
      }
      var args = collectArgs(card);
      var prefill = sessionStorage.getItem("prefill_ticker");
      if (prefill && rid === "judge-lifecycle" && !args.ticker) {
        args.ticker = prefill;
        var tickerInput = card.querySelector("input[name='arg-ticker']");
        if (tickerInput) tickerInput.value = prefill;
        sessionStorage.removeItem("prefill_ticker");
      }
      appendConsole("▶ " + rid + " …");
      card.classList.add("running");
      var body = { args: args };
      if (needsConfirm) body.confirm_name = confirmName;
      fetch("/run/" + encodeURIComponent(rid), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) {
            appendConsole("refused: " + data.error);
            card.classList.remove("running");
            return;
          }
          streamRun(data.run_id, card);
        })
        .catch(function (e) {
          appendConsole("request failed: " + e);
          card.classList.remove("running");
        });
    });
  });

  restoreConsole();
  var dock = $("#console-dock");
  if (dock) {
    var summary = dock.querySelector("summary");
    if (summary && !summary.querySelector(".console-clear")) {
      var clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "console-clear";
      clearBtn.textContent = "Clear";
      clearBtn.style.cssText = "margin-left:0.75rem;font-size:0.72rem";
      clearBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        sessionStorage.removeItem(CONSOLE_KEY);
        var el = $("#console-output");
        if (el) el.textContent = "(empty — launch a routine from Runs)";
      });
      summary.appendChild(clearBtn);
    }
  }
})();
