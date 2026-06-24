// Live-data sidecar for the Crucible design bundle.
//
// The .dc.html pages are the verbatim Claude Design UI; this script replaces the
// stubbed data with live backend data without changing the UI markup. It binds
// to nodes the pages tag with `data-live="<key>"` (a single attribute on the
// existing data node, no structural change), and opens the SSE stream so the
// attack-success-rate readout updates live (US-2).
//
// The page renders asynchronously (support.js pulls React/Babel, then mounts),
// so binding polls briefly for the tagged nodes before giving up.
(function () {
  "use strict";

  function json(path) {
    return fetch(path)
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  function pct(x) {
    return x === null || x === undefined ? "—" : (x * 100).toFixed(1) + "%";
  }

  function setText(key, value) {
    var nodes = document.querySelectorAll('[data-live="' + key + '"]');
    nodes.forEach(function (el) {
      if (value !== null && value !== undefined) el.textContent = String(value);
    });
    return nodes.length;
  }

  function hasHooks() {
    return document.querySelector("[data-live],[data-live-list]") !== null;
  }

  async function wireMetrics() {
    var m = await json("/metrics");
    if (!m) return;
    setText("black_box_rate", pct(m.black_box_catch_rate.rate));
    setText("white_box_rate", pct(m.white_box_catch_rate.rate));
    setText("catch_gap", pct(m.catch_rate_gap));
    setText("black_box_judged", m.black_box_catch_rate.judged);
    setText("white_box_judged", m.white_box_catch_rate.judged);
  }

  async function wireHealth() {
    var h = await json("/health");
    if (h) setText("db_status", h.database);
  }

  async function wireList(key, path, render) {
    var host = document.querySelector('[data-live-list="' + key + '"]');
    if (!host) return;
    var rows = await json(path);
    if (!Array.isArray(rows)) return;
    host.innerHTML = "";
    rows.forEach(function (row) { host.appendChild(render(row)); });
  }

  function catalogRow(r) {
    var div = document.createElement("div");
    div.setAttribute("data-live-row", "catalog");
    div.style.cssText =
      "display:flex;gap:16px;padding:10px 0;border-bottom:1px solid #232E39;" +
      "font-family:'IBM Plex Mono',monospace;font-size:12px;color:#B8C2CE";
    div.textContent =
      r.tactic + "  ·  " + r.target_type + "  ·  reuse " + r.reuse_count +
      "  ·  $" + (r.avg_dollars_to_succeed || 0).toFixed(4);
    return div;
  }

  function wireSse() {
    var runId = new URLSearchParams(location.search).get("run");
    if (!runId) return;
    var total = 0, succeeded = 0;
    var es = new EventSource("/runs/" + runId + "/stream");
    es.addEventListener("attack", function (e) {
      total += 1;
      try { if (JSON.parse(e.data).succeeded) succeeded += 1; } catch (_) {}
      setText("asr", pct(total ? succeeded / total : 0));
      setText("attack_count", total);
    });
    es.addEventListener("run_status", function () { es.close(); });
    es.onerror = function () { es.close(); };
    window.CrucibleLive.sse = es;
  }

  async function wireHaltBanner() {
    // The halt banner must appear on EVERY route (US-13), so it is independent
    // of any per-page data hook. Injected once, pinned to the top, dismiss not
    // offered: a halted certification is not something the operator waves away.
    if (document.getElementById("crucible-halt-banner")) return;
    var h = await json("/halt");
    if (!h || !h.halted) return;
    var bar = document.createElement("div");
    bar.id = "crucible-halt-banner";
    bar.setAttribute("role", "alert");
    bar.style.cssText =
      "position:sticky;top:0;z-index:9999;background:#7A1F1F;color:#FFE8E8;" +
      "font-family:'IBM Plex Mono',monospace;font-size:13px;padding:10px 16px;" +
      "text-align:center;border-bottom:1px solid #B23A3A";
    bar.innerHTML =
      h.message + ' · <a href="/metrics" style="color:#FFD7D7">view metrics</a>';
    document.body.insertBefore(bar, document.body.firstChild);
  }

  async function wire() {
    await Promise.all([
      wireMetrics(),
      wireHealth(),
      wireList("catalog", "/catalog", catalogRow),
    ]);
    wireSse();
  }

  window.CrucibleLive = { json: json, wire: wire, wireHaltBanner: wireHaltBanner };

  // The halt banner is route-independent; poll briefly for the mounted body.
  var haltTicks = 0;
  var haltTimer = setInterval(function () {
    haltTicks += 1;
    if (document.body) {
      clearInterval(haltTimer);
      wireHaltBanner();
    } else if (haltTicks > 50) {
      clearInterval(haltTimer);
    }
  }, 200);

  // The page mounts asynchronously; poll briefly for the tagged nodes, then bind.
  var ticks = 0;
  var timer = setInterval(function () {
    ticks += 1;
    if (hasHooks() || new URLSearchParams(location.search).get("run")) {
      clearInterval(timer);
      wire();
    } else if (ticks > 50) {
      clearInterval(timer); // ~10s: page has no live hooks, leave it verbatim
    }
  }, 200);
})();
