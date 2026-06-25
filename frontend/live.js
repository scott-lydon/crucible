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
    // Undetected-hack rate (dashboard headline) is the complement of the
    // white-box catch rate: the share of attacks that got past the verifier.
    var wb = m.white_box_catch_rate.rate;
    setText("undetected_rate", wb === null || wb === undefined ? "—" : pct(1 - wb));
  }

  function runRow(r) {
    var div = document.createElement("div");
    div.setAttribute("data-live-row", "runs");
    div.style.cssText =
      "display:flex;gap:16px;padding:11px 22px;border-bottom:1px solid #1D2630;" +
      "font-family:'IBM Plex Mono',monospace;font-size:12.5px;color:#B8C2CE";
    var rid = document.createElement("a");
    rid.href = "slice-02-live-run-view.dc.html?run=" + encodeURIComponent(r.run_id);
    rid.style.cssText = "color:#4FAAC0;text-decoration:underline;min-width:90px";
    rid.textContent = (r.run_id || "").slice(0, 8);
    var meta = document.createElement("span");
    meta.textContent =
      shortDate(r.created_at) + " · " + r.target_type + " · " + r.status +
      " · " + (r.spec_title || "");
    div.appendChild(rid);
    div.appendChild(meta);
    return div;
  }

  async function wireHealth() {
    var h = await json("/health");
    if (h) setText("db_status", h.database);
  }

  async function wireHalt() {
    // The halt certification page (slice-08) reads the real /halt state: the
    // platform halts certification when white-box recall falls below the red
    // line (US-13). A fresh deployment with recall above the line is not halted,
    // so the page honestly says "no active halt" rather than the design bundle's
    // hardcoded active-halt scenario. The backend halt is a single current
    // state; the design's blocked-run queue, halt history, and lift workflow
    // have no backing route and were removed (see REMOVED_UI.md).
    var h = await json("/halt");
    if (!h) return;
    if (h.halted) {
      setText("halt.state_label", "Halt active");
      setText("halt.recall", h.recall === null ? "—" : Number(h.recall).toFixed(2));
      setText("halt.threshold", "recall >= " + Number(h.threshold).toFixed(2));
      setText("halt.message", h.message || "certification halted");
    } else {
      setText("halt.state_label", "no active halt");
      setText("halt.recall", h.recall === null ? "—" : Number(h.recall).toFixed(2));
      setText("halt.threshold", "recall >= " + Number(h.threshold).toFixed(2));
      setText("halt.message", "no active halt · certification is not blocked");
    }
  }

  async function wireList(key, path, render) {
    var host = document.querySelector('[data-live-list="' + key + '"]');
    if (!host) return;
    var rows = await json(path);
    // Keep the design's in-markup empty state when the route is unreachable or
    // returns nothing, so a fresh deployment shows "no … yet" rather than a
    // blank panel; only replace the host once there is real data to render.
    if (!Array.isArray(rows) || rows.length === 0) return;
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

  function specHistoryRow(r) {
    // One sealed-spec timeline entry (slice-16) from /specs/history. The design
    // bundle's approved/retired states, patch counts, diff, signatures, and
    // provenance chain have no backing route and were removed (REMOVED_UI.md);
    // this renders the real spec id, title, obligation count, and seal date.
    var wrap = document.createElement("div");
    wrap.setAttribute("data-live-row", "specs_history");
    wrap.style.cssText = "display:flex;gap:18px;align-items:flex-start;padding-bottom:18px";
    var title = r.title || r.spec_id;
    var meta =
      (r.spec_id || "").slice(0, 8) + " · sealed " + shortDate(r.created_at) +
      " · " + r.obligations + " obligations";
    wrap.innerHTML =
      '<span style="width:14px;height:14px;border-radius:50%;background:#4FAAC0;' +
      'border:3px solid #0E141B;flex:none;margin-left:8px;margin-top:4px"></span>' +
      '<div style="flex:1"><div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">' +
      '<span style="font-family:\'IBM Plex Mono\',monospace;color:#E8EDF3;font-size:14px"></span>' +
      '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:#B8C2CE"></span>' +
      "</div></div>";
    var spans = wrap.querySelectorAll("span");
    spans[1].textContent = title;
    spans[2].textContent = meta;
    return wrap;
  }

  function fmtNum(x) {
    return x === null || x === undefined ? "—" : String(x);
  }

  async function wirePolicy() {
    // slice-15 reads the real operative governance policy from /policy.
    var p = await json("/policy");
    if (!p) return;
    setText("policy.operative", p.operative_policy || "—");
    setText("policy.threshold", p.halt_recall_threshold);
    setText("policy.custom", p.custom_policy_yaml || "no custom policy set");
  }

  function overrideRow(o) {
    var div = document.createElement("div");
    div.setAttribute("data-live-row", "overrides");
    div.style.cssText =
      "display:flex;gap:16px;padding:10px 18px;border-bottom:1px solid #1D2630;" +
      "font-family:'IBM Plex Mono',monospace;font-size:12.5px;color:#B8C2CE";
    div.textContent =
      shortDate(o.created_at) + " · " + o.actor + " · " + o.field + " = " + o.value +
      (o.run_id ? " · run " + String(o.run_id).slice(0, 8) : "");
    return div;
  }

  function healthCard(name, role, probe) {
    var status = (probe && probe.status) || "amber";
    var dot = status === "green" ? "#57C08A" : status === "red" ? "#E5736B" : "#D9A441";
    var card = document.createElement("div");
    card.setAttribute("data-live-row", "health");
    card.style.cssText =
      "border:1px solid #2C3744;border-radius:12px;background:#161E27;padding:22px;" +
      "display:flex;flex-direction:column;gap:12px";
    var head = document.createElement("div");
    head.style.cssText = "display:flex;align-items:center;gap:10px";
    head.innerHTML =
      '<span style="width:9px;height:9px;border-radius:50%;flex:none"></span>' +
      '<span style="font-size:14.5px;font-weight:600;color:#E8EDF3"></span>' +
      '<span style="flex:1"></span>' +
      '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;letter-spacing:.1em;color:#7C8896;text-transform:uppercase"></span>';
    var hs = head.querySelectorAll("span");
    hs[0].style.background = dot;
    hs[1].textContent = name;
    hs[3].textContent = role + " · " + status;
    var detail = document.createElement("div");
    detail.style.cssText =
      "font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:#8A94A2;line-height:1.55";
    var d = (probe && probe.detail) || {};
    detail.textContent = Object.keys(d).slice(0, 4).map(function (k) {
      return k + ": " + d[k];
    }).join(" · ") || "no detail";
    card.appendChild(head);
    card.appendChild(detail);
    return card;
  }

  async function wireHealthGrid() {
    // slice-11 renders the REAL self-test status of each registered target and
    // oracle (US-8) from /targets/registered + /health/targets/{type} and
    // /oracles/registered + /health/oracles/{name}, replacing the design
    // bundle's static infra leaves and incident log (out of PRD, removed —
    // REMOVED_UI.md).
    var host = document.querySelector('[data-live-list="health"]');
    if (!host) return;
    var targets = (await json("/targets/registered")) || [];
    var oraclesResp = (await json("/oracles/registered")) || {};
    var oracles = oraclesResp.oracles || [];
    var cards = [];
    for (var i = 0; i < targets.length; i++) {
      var th = await json("/health/targets/" + targets[i].type);
      cards.push(healthCard(targets[i].display_name || targets[i].type, "target", th));
    }
    for (var j = 0; j < oracles.length; j++) {
      var oh = await json("/health/oracles/" + oracles[j].name);
      cards.push(healthCard(oracles[j].name, "oracle", oh));
    }
    if (cards.length === 0) return;
    host.innerHTML = "";
    cards.forEach(function (c) { host.appendChild(c); });
  }

  async function wireBluePatch() {
    // slice-07 reads /blue/{patchId} from a ?patch=<id> URL parameter and
    // renders the real patch (kind, held-out detection before/after, the
    // produced model version), or "no patch selected" when absent. The design
    // bundle's fabricated reviewer-actions/approval workflow has no backing
    // route and is removed (REMOVED_UI.md).
    var host = document.querySelector('[data-live="blue_patch"]');
    if (!host) return;
    var id = new URLSearchParams(location.search).get("patch");
    if (!id) { host.textContent = "no patch selected"; return; }
    var p = await json("/blue/" + encodeURIComponent(id));
    if (!p || !p.patch_id) { host.textContent = "no patch for id " + id; return; }
    var ho = (p.holdout_runs && p.holdout_runs[0]) || {};
    var mv = (p.model_versions && p.model_versions[0]) || {};
    var rows = [
      ["patch", p.patch_id],
      ["target", p.target_type],
      ["kind", p.kind],
      ["held-out size", fmtNum(ho.holdout_size)],
      ["detection before", fmtNum(ho.detection_before)],
      ["detection after", fmtNum(ho.detection_after)],
      ["recovered", ho.recovered === true ? "yes" : ho.recovered === false ? "no" : "—"],
      ["model version", mv.version != null ? "v" + mv.version : "—"],
      ["artifact", mv.artifact_ref || "—"],
    ];
    host.innerHTML = "";
    rows.forEach(function (r) {
      var line = document.createElement("div");
      line.style.cssText =
        "display:flex;justify-content:space-between;gap:18px;padding:9px 0;" +
        "border-bottom:1px solid #1D2630;font-family:'IBM Plex Mono',monospace;font-size:13px";
      var k = document.createElement("span");
      k.style.color = "#B8C2CE";
      k.textContent = r[0];
      var v = document.createElement("span");
      v.style.color = "#E8EDF3";
      v.textContent = String(r[1]);
      line.appendChild(k);
      line.appendChild(v);
      host.appendChild(line);
    });
  }

  async function wireReport() {
    // slice-14 renders the SR 11-7 report for a real run from /reports/{runId}
    // when a ?run=<id> URL parameter is present, else "no run selected". The
    // backend returns the report as Markdown (numbers linked to their real
    // verdict/attack rows); the design bundle's fabricated KPI grid and static
    // sections are replaced by this real rendered report.
    var host = document.querySelector('[data-live="report"]');
    if (!host) return;
    var runId = new URLSearchParams(location.search).get("run");
    if (!runId) { host.textContent = "no run selected"; return; }
    var r = await json("/reports/" + encodeURIComponent(runId));
    if (!r || !r.markdown) { host.textContent = "no report for run " + runId; return; }
    var pre = document.createElement("pre");
    pre.style.cssText =
      "white-space:pre-wrap;font-family:'IBM Plex Mono',monospace;font-size:12.5px;" +
      "color:#1A2330;margin:0;line-height:1.6";
    pre.textContent = r.markdown;
    host.innerHTML = "";
    host.appendChild(pre);
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

  function money(n) {
    return n === null || n === undefined ? "—" : "$" + Number(n).toFixed(2);
  }

  function shortDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return (
      d.getUTCFullYear() +
      "-" +
      String(d.getUTCMonth() + 1).padStart(2, "0") +
      "-" +
      String(d.getUTCDate()).padStart(2, "0")
    );
  }

  async function wireLauncher() {
    // Wire the static stub values on slice-01-run-launcher.dc.html to the real
    // routes the backend now serves. Every value below previously displayed a
    // hardcoded stub from the design bundle; now each reads from the source the
    // route names. Null fields render as em-dash by design, so a fresh deploy
    // never shows a fabricated figure (no-stub-data rule).
    var me = await json("/me");
    if (me) {
      setText("me.display_name", me.display_name || "—");
      setText("me.audit_log_target", me.audit_log_target || "no audit identity");
      setText("me.role_chip", me.role || "no role");
      setText("me.role_line", "ROLE · " + (me.role || "no role"));
      setText(
        "me.identity_line",
        (me.display_name || "anonymous") + " · default workspace",
      );
    }
    var ws = await json("/workspace");
    if (ws) {
      setText("workspace.name", ws.name || "—");
    }
    var spend = await json("/spend/current-month");
    if (spend) {
      setText("spend.current", money(spend.spent_dollars));
      setText(
        "spend.ceiling",
        spend.ceiling_dollars === null ? "no ceiling" : money(spend.ceiling_dollars),
      );
    }
    var health = await json("/health");
    if (health) {
      setText(
        "health.live_label",
        "Live · " + (health.database === "connected" ? "connected" : "database " + health.database),
      );
    }
    var targets = await json("/targets/registered");
    if (Array.isArray(targets)) {
      var byType = {};
      targets.forEach(function (t) { byType[t.type] = t; });
      if (byType.fraud) {
        setText("targets.fraud.artifact_ref", byType.fraud.artifact_ref);
      }
      if (byType.code_agent) {
        setText("targets.code_agent.artifact_ref", byType.code_agent.artifact_ref);
      }
      var disabled = Math.max(0, 3 - targets.length);
      setText(
        "targets.disabled_summary",
        disabled === 0 ? "all adapters registered" : disabled + " adapter(s) disabled",
      );
    }
    var fraudHealth = await json("/health/targets/fraud");
    if (fraudHealth && fraudHealth.detail && fraudHealth.detail.trained_at) {
      setText(
        "targets.fraud.validated_at",
        "validated " + shortDate(fraudHealth.detail.trained_at),
      );
    } else {
      setText("targets.fraud.validated_at", "not yet validated");
    }
    var codeHealth = await json("/health/targets/code_agent");
    if (codeHealth && codeHealth.status === "green") {
      setText("targets.code_agent.validated_at", "validated (ready)");
    } else if (codeHealth) {
      setText("targets.code_agent.validated_at", "not yet validated");
    }
    var oracles = await json("/oracles/registered");
    if (oracles) {
      var nonJudge = oracles.oracles.filter(function (o) { return !/judge/i.test(o.name); }).length;
      var hasJudge = oracles.oracles.some(function (o) { return /judge/i.test(o.name); });
      setText(
        "oracles.summary",
        nonJudge + (hasJudge ? " + judge" : ""),
      );
      if (oracles.judge_share_text) {
        setText("oracles.judge_share_text", oracles.judge_share_text);
      }
    }
    // History strip + estimate-drawer prior-runs table read /runs (newest first).
    var runs = await json("/runs");
    if (Array.isArray(runs)) {
      if (runs.length === 0) {
        setText("history.latest_run_label", "no runs yet");
        setText("history.oldest_run_label", "");
        setText("estimate.prior_runs.r1_id", "no prior runs");
      } else {
        var newest = runs[0];
        var oldest = runs[runs.length - 1];
        setText(
          "history.latest_run_label",
          shortDate(newest.created_at) + " · " + newest.run_id.slice(0, 6),
        );
        setText("history.oldest_run_label", shortDate(oldest.created_at));
        var slots = [1, 2, 3, 4];
        slots.forEach(function (i) {
          var row = runs[i - 1];
          if (!row) {
            setText("estimate.prior_runs.r" + i + "_id", "");
            setText("estimate.prior_runs.r" + i + "_cost", "");
            return;
          }
          var suffix = i === 1 ? ' <span style="color:#4FAAC0">·current</span>' : "";
          setText("estimate.prior_runs.r" + i + "_id", row.run_id.slice(0, 8) + suffix);
          setText("estimate.prior_runs.r" + i + "_cost", "—");
        });
      }
    }
    // /estimate runs over the page's default 48-round budget against the fraud
    // target (the selected card on the run launcher). The route returns nulls
    // when no prior runs exist, which render as em-dash.
    var est = await json("/estimate?target_type=fraud&rounds=48");
    if (est) {
      var perRound =
        est.cost_per_round_dollars === null
          ? "not yet measured"
          : money(est.cost_per_round_dollars) + " per round";
      setText("estimate.per_round_text", perRound);
      setText("estimate.projected_text", money(est.high_dollars));
      // Estimate-drawer subtitle and avg-per-round narrative
      var subtitle =
        est.cost_per_round_dollars === null
          ? "no prior runs to estimate from"
          : money(est.cost_per_round_dollars) + " / round (n=" + est.sample_attacks + ")";
      setText("estimate.subtitle", subtitle);
      setText(
        "estimate.avg_per_round_blurb",
        est.cost_per_round_dollars === null
          ? "not yet measured"
          : money(est.cost_per_round_dollars) +
              " (over " +
              est.sample_attacks +
              " prior fraud attacks)",
      );
    }
    // Running tab: until a real run is selected via URL (?run=...), the run
    // header, current strategy and per-round costs honestly say nothing is
    // active. live SSE wiring fills these once the operator launches a run.
    var runIdParam = new URLSearchParams(location.search).get("run");
    if (!runIdParam) {
      setText("running.run_header", "no run started");
      setText("running.last_round_cost", "—");
      setText("running.avg_round_cost", "—");
      setText("running.current_tactic", "—");
      setText("running.current_seed", "—");
    }
    var sandbox = await json("/sandbox/image");
    if (sandbox) {
      setText("sandbox.image", sandbox.image);
    }
  }

  function postJson(path, body) {
    // POST helper for the two write routes the launcher drives (create run,
    // start run). Resolves to the parsed body on 2xx; rejects with an Error
    // carrying the route, status, and the backend's curated `detail` message so
    // a failed launch surfaces exactly what to fix rather than a silent no-op.
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) {
      return r
        .json()
        .catch(function () { return null; })
        .then(function (data) {
          if (r.ok) return data;
          var detail = data && data.detail ? data.detail : r.statusText;
          throw new Error("POST " + path + " failed (" + r.status + "): " + detail);
        });
    });
  }

  // Launcher interaction state. The design ships the Fraud card pre-selected, so
  // that is the initial selection; clicking a card moves the selection and
  // re-renders the sealed-spec panel, run-summary target, and the Run button's
  // launch target. No markup is authored here (design-fidelity rule): the
  // sidecar finds the design's own nodes by their stable content and rewrites
  // only the data they carry.
  var launcherSelection = { target_type: "fraud", artifact_refs: {}, displayNames: {} };

  function cardsRow() {
    // Lowest common ancestor of the two target cards' artifact-ref nodes is the
    // flex row that holds both cards. Found by node identity, never by style
    // string, so it survives React re-serializing inline styles (e.g.
    // "min-width:200px" rendered back as "min-width: 200px").
    var a = document.querySelector('[data-live="targets.fraud.artifact_ref"]');
    var b = document.querySelector('[data-live="targets.code_agent.artifact_ref"]');
    if (!a || !b) return null;
    var ancestors = [];
    for (var n = a; n; n = n.parentElement) ancestors.push(n);
    for (var m = b; m; m = m.parentElement) {
      if (ancestors.indexOf(m) >= 0) return m;
    }
    return null;
  }

  function findTargetCard(targetType) {
    var ref = document.querySelector(
      '[data-live="targets.' + targetType + '.artifact_ref"]'
    );
    var row = cardsRow();
    if (!ref || !row) return null;
    // The card is the direct child of the cards row that contains this ref.
    var node = ref;
    while (node && node.parentElement && node.parentElement !== row) {
      node = node.parentElement;
    }
    return node && node.parentElement === row ? node : null;
  }

  function styleCardSelected(card, selected) {
    if (!card) return;
    card.style.background = selected ? "#16242A" : "#161E27";
    card.style.borderColor = selected ? "#2E5560" : "#2C3744";
    var badge = card.querySelector("[data-live-selected-badge]");
    if (selected && !badge) {
      // Append the ✓ chip to the card's header row (its first element child),
      // which holds the icon + name; no style-string matching needed.
      var header = card.firstElementChild || card;
      badge = document.createElement("span");
      badge.setAttribute("data-live-selected-badge", "1");
      badge.style.cssText =
        "margin-left:auto;width:16px;height:16px;border-radius:50%;background:#4FAAC0;" +
        "display:flex;align-items:center;justify-content:center;color:#0E141B;" +
        "font-size:11px;font-weight:700";
      badge.textContent = "✓";
      header.appendChild(badge);
    } else if (!selected && badge) {
      badge.remove();
    }
  }

  async function renderSealedSpec(targetType) {
    // Replace the design's hardcoded fraud YAML with the real sealed spec the
    // backend will seal this run under (GET /targets/{type}/default-spec).
    // Match the element that DIRECTLY owns the ".sealed.yaml" filename text
    // (a sibling text node next to the yaml icon), not an ancestor whose
    // textContent merely contains it via descendants. Matching on textContent
    // picked the page-root wrapper, whose lastChild is the whole launcher, so
    // overwriting lastChild.textContent blanked the entire page.
    var header = Array.prototype.find.call(
      document.querySelectorAll("div,span"),
      function (el) {
        return Array.prototype.some.call(el.childNodes, function (n) {
          return n.nodeType === 3 && /\.sealed\.yaml/.test(n.nodeValue || "");
        });
      }
    );
    if (!header) return;
    var spec = await json("/targets/" + targetType + "/default-spec");
    if (!spec || !spec.yaml) return;
    header.lastChild.textContent =
      " spec." + targetType + ".sealed.yaml · " + spec.yaml.split("\n").length + " lines";
    // The code body is the header's next sibling inside the bordered panel.
    var body = header.nextElementSibling;
    if (!body) return;
    body.innerHTML = "";
    spec.yaml.split("\n").forEach(function (line, i) {
      var row = document.createElement("div");
      row.style.cssText = "display:flex";
      row.innerHTML =
        '<span style="width:34px;flex:none;text-align:right;padding:0 10px;color:#95A1AE;' +
        'border-right:1px solid #1D2630"></span>' +
        '<span style="padding:0 14px;color:#B8C2CE"></span>';
      row.children[0].textContent = String(i + 1);
      row.children[1].textContent = line;
      body.appendChild(row);
    });
  }

  function setRunSummaryTarget(displayName) {
    var label = Array.prototype.find.call(
      document.querySelectorAll("span"),
      function (el) { return (el.textContent || "").trim() === "Target" && el.nextElementSibling; }
    );
    if (label && label.nextElementSibling) {
      label.nextElementSibling.textContent = displayName;
    }
  }

  function readBudgetInputs() {
    var inputs = Array.prototype.slice.call(document.querySelectorAll("input"));
    var roundsEl = inputs.find(function (i) { return !String(i.value).includes("$"); });
    var ceilingEl = inputs.find(function (i) { return String(i.value).includes("$"); });
    var rounds = roundsEl ? parseInt(String(roundsEl.value).replace(/[^0-9]/g, ""), 10) : NaN;
    var ceiling = ceilingEl
      ? parseFloat(String(ceilingEl.value).replace(/[^0-9.]/g, ""))
      : NaN;
    return {
      rounds: Number.isFinite(rounds) && rounds > 0 ? rounds : 48,
      ceiling: Number.isFinite(ceiling) && ceiling > 0 ? ceiling : 25,
    };
  }

  function findRunButton() {
    return Array.prototype.find.call(
      document.querySelectorAll("button"),
      function (b) { return /run evaluation/i.test(b.textContent || ""); }
    );
  }

  function showLauncherError(message) {
    var btn = findRunButton();
    if (!btn) return;
    var box = document.getElementById("crucible-launch-error");
    if (!box) {
      box = document.createElement("div");
      box.id = "crucible-launch-error";
      box.style.cssText =
        "margin-top:10px;padding:10px 12px;background:#2A1517;border:1px solid #5A2A2C;" +
        "border-radius:6px;color:#E5B5B0;font-family:'IBM Plex Mono',monospace;font-size:11.5px;" +
        "line-height:1.5;white-space:pre-wrap";
      btn.parentElement.insertBefore(box, btn.nextSibling);
    }
    box.textContent = message;
  }

  function clearLauncherError() {
    var box = document.getElementById("crucible-launch-error");
    if (box) box.remove();
  }

  async function launchRun() {
    var btn = findRunButton();
    if (!btn || btn.dataset.launching === "1") return;
    clearLauncherError();
    var targetType = launcherSelection.target_type;
    var artifactRef = launcherSelection.artifact_refs[targetType];
    if (!artifactRef) {
      showLauncherError(
        "Cannot launch: no registered artifact for target '" + targetType +
        "'. The target is not wired into the registry (GET /targets/registered)."
      );
      return;
    }
    var originalText = btn.textContent;
    btn.dataset.launching = "1";
    btn.disabled = true;
    btn.textContent = "Launching…";
    try {
      var specResp = await json("/targets/" + targetType + "/default-spec");
      if (!specResp || !specResp.spec) {
        throw new Error("GET /targets/" + targetType + "/default-spec returned no spec");
      }
      var budget = readBudgetInputs();
      var created = await postJson("/runs", {
        target_type: targetType,
        artifact_ref: artifactRef,
        spec: specResp.spec,
        budget: { max_attempts: budget.rounds, max_dollars: budget.ceiling },
      });
      if (!created || !created.run_id) {
        throw new Error("POST /runs returned no run_id");
      }
      await postJson("/runs/" + created.run_id + "/start", {});
      location.href =
        "slice-02-live-run-view.dc.html?run=" + encodeURIComponent(created.run_id);
    } catch (err) {
      btn.dataset.launching = "0";
      btn.disabled = false;
      btn.textContent = originalText;
      showLauncherError(String(err && err.message ? err.message : err));
    }
  }

  async function selectTarget(targetType) {
    if (!launcherSelection.artifact_refs[targetType]) return;
    launcherSelection.target_type = targetType;
    var types = Object.keys(launcherSelection.artifact_refs);
    types.forEach(function (t) {
      styleCardSelected(findTargetCard(t), t === targetType);
    });
    setRunSummaryTarget(launcherSelection.displayNames[targetType] || targetType);
    await renderSealedSpec(targetType);
  }

  async function wireLauncherActions() {
    // Only the Run Launcher carries the target cards + Run button; on every
    // other page these selectors find nothing and this is a no-op.
    var targets = await json("/targets/registered");
    if (!Array.isArray(targets)) return;
    var launchable = targets.filter(function (t) {
      return t.type === "fraud" || t.type === "code_agent";
    });
    if (launchable.length === 0) return;
    launchable.forEach(function (t) {
      launcherSelection.artifact_refs[t.type] = t.artifact_ref;
      launcherSelection.displayNames[t.type] = t.display_name || t.type;
      var card = findTargetCard(t.type);
      if (card) {
        card.style.cursor = "pointer";
        card.addEventListener("click", function () { selectTarget(t.type); });
      }
    });
    var btn = findRunButton();
    if (btn) btn.addEventListener("click", function (e) { e.preventDefault(); launchRun(); });
    // Render the real sealed spec for the initially-selected target.
    await selectTarget(launcherSelection.target_type);
  }

  async function wire() {
    await Promise.all([
      wireMetrics(),
      wireHealth(),
      wireHalt(),
      wireList("catalog", "/catalog", catalogRow),
      wireList("specs_history", "/specs/history", specHistoryRow),
      wireReport(),
      wireBluePatch(),
      wireHealthGrid(),
      wireList("runs", "/runs", runRow),
      wirePolicy(),
      wireList("overrides", "/admin/overrides", overrideRow),
      wireLauncher(),
    ]);
    await wireLauncherActions();
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
