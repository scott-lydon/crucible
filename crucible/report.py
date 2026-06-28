"""Slice 6: ``crucible report`` — a static report site that is a PURE renderer.

The site reads ONLY the run's artifact files. Every metric slot in the HTML is an empty
DOM node filled by JavaScript from the artifact data inlined as a JSON blob, so the
template itself carries zero numeric literals and a missing ``metrics.json`` renders
"Not yet measured" instead of a hardcoded zero. This is what structurally kills the
facade class: the dashboard can only show what a real run actually wrote.

The unit test (test matrix row ``crucible/report``) asserts: no numeric literal in a
metric slot of the template, and deleting metrics.json flips the card to "Not yet
measured"."""

# The HTML/CSS template lines below are intentionally long; E501 is waived file-wide.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
from pathlib import Path
from typing import Any

from crucible.artifacts import RunArtifacts, list_runs
from shared.obs.emit import read_trace


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _collect(run_id: str) -> dict[str, Any]:
    arts = RunArtifacts.for_run(run_id)
    events = [e.to_dict() for e in read_trace(run_id)]
    verdicts = []
    vdir = arts.root / "verdicts"
    if vdir.exists():
        for f in sorted(vdir.glob("*.json")):
            if f.name.endswith(".replay.json"):
                continue
            verdicts.append(json.loads(f.read_text(encoding="utf-8")))
    catalog = []
    if arts.catalog.exists():
        catalog = [json.loads(ln) for ln in arts.catalog.read_text(encoding="utf-8").splitlines()
                   if ln.strip()]
    return {
        "run_id": run_id,
        "events": events,
        "verdicts": verdicts,
        "catalog": catalog,
        "metrics": _read_json(arts.metrics),         # None => "Not yet measured"
        "eligibility": _read_json(arts.eligibility),
        "suitability": _read_json(arts.suitability),
    }


# The metric slots are EMPTY (data-metric=...) — JS fills them from DATA at load. There is
# no numeric literal in any metric slot, so the facade-grep stays clean.
_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Crucible report — {run_id}</title>
<style>
 body{{font-family:ui-monospace,Menlo,monospace;background:#0a0e1a;color:#e2e8f0;margin:0;padding:24px}}
 h1,h2{{color:#fff}} .muted{{color:#94a3b8}}
 .cards{{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}}
 .card{{background:#1a2236;border:1px solid #2a3550;border-radius:8px;padding:14px 18px;min-width:180px}}
 .card .v{{font-size:1.6em;color:#6366f1}} .card .l{{font-size:.8em}}
 table{{border-collapse:collapse;width:100%;margin:8px 0}}
 td,th{{border:1px solid #2a3550;padding:6px 8px;text-align:left;font-size:.85em}}
 .pass{{color:#22c55e}} .fail{{color:#ef4444}}
 .ev{{padding:2px 0;font-size:.85em}} .seq{{color:#64748b}}
 details{{margin:6px 0}} summary{{cursor:pointer}}
</style></head><body>
<h1>Crucible run <span class="muted">{run_id}</span></h1>
<p class="muted">Pure renderer: every number below is read from this run's artifact files.
A blank metric means the run did not measure it.</p>
<div id="header"></div>
<h2>Headline metrics</h2>
<div class="cards">
 <div class="card"><div class="v" data-metric="white_box_catch_rate"></div><div class="l">White-box catch rate</div></div>
 <div class="card"><div class="v" data-metric="black_box_catch_rate"></div><div class="l">Black-box catch rate</div></div>
 <div class="card"><div class="v" data-metric="validation_vs_holdout_gap"></div><div class="l">BB vs WB gap</div></div>
 <div class="card"><div class="v" data-metric="undetected_hack_rate"></div><div class="l">Undetected-hack rate</div></div>
 <div class="card"><div class="v" data-metric="dollars_per_caught_hack"></div><div class="l">$ / caught hack</div></div>
</div>
<h2>Co-evolution &amp; ASR (from trace)</h2>
<div id="coevo"></div>
<h2>Strategy leaderboard (undetected tactics)</h2>
<div id="catalog"></div>
<h2>Verdicts</h2>
<div id="verdicts"></div>
<h2>Trace timeline</h2>
<div id="trace"></div>
<script id="data" type="application/json">{data_json}</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const NM = '<span class="muted">Not yet measured</span>';
function pct(v){{return (v===null||v===undefined)?NM:(v*100).toFixed(1)+'%';}}
function usd(v){{return (v===null||v===undefined)?NM:'$'+Number(v).toFixed(4);}}
// Header: grades from eligibility + suitability so a reader does not over-trust a thin verdict.
(function(){{
 const e=DATA.eligibility, s=DATA.suitability; let h='';
 if(e) h+='<span class="card">Eligibility: '+e.verdict+'</span> ';
 if(s) h+='<span class="card">Suitability: '+s.grade+'</span>';
 document.getElementById('header').innerHTML=h;
}})();
// Metric slots: filled ONLY from DATA.metrics.tiles; null/absent -> "Not yet measured".
(function(){{
 const tiles=(DATA.metrics&&DATA.metrics.tiles)||{{}};
 document.querySelectorAll('[data-metric]').forEach(el=>{{
  const k=el.getAttribute('data-metric'); const v=tiles[k];
  el.innerHTML = (k==='dollars_per_caught_hack') ? usd(v) : pct(v);
 }});
}})();
// Co-evolution / ASR curve from metric_update events that carry asr/detection.
(function(){{
 const rows=DATA.events.filter(e=>e.type==='metric_update'&&(e.data.asr!=null||e.data.detection!=null));
 if(!rows.length){{document.getElementById('coevo').innerHTML=NM;return;}}
 let t='<table><tr><th>round</th><th>ASR</th><th>detection</th></tr>';
 rows.forEach((r,i)=>{{t+='<tr><td>'+(r.data.round??i)+'</td><td>'+pct(r.data.asr)+'</td><td>'+pct(r.data.detection)+'</td></tr>';}});
 document.getElementById('coevo').innerHTML=t+'</table>';
}})();
// Strategy leaderboard from catalog.jsonl.
(function(){{
 const c=DATA.catalog;
 if(!c.length){{document.getElementById('catalog').innerHTML='<p class="muted">No undetected tactics recorded.</p>';return;}}
 let t='<table><tr><th>#</th><th>tactic / verdict</th><th>outcome</th></tr>';
 c.forEach((r,i)=>{{t+='<tr><td>'+(i+1)+'</td><td>'+(r.tactic||r.attack_id||r.verdict_id||'?')+'</td><td>'+(r.outcome||'')+'</td></tr>';}});
 document.getElementById('catalog').innerHTML=t+'</table>';
}})();
// Verdict drill-down.
(function(){{
 const v=DATA.verdicts;
 if(!v.length){{document.getElementById('verdicts').innerHTML='<p class="muted">No verdicts.</p>';return;}}
 let h='';
 v.forEach(vd=>{{
  let votes='<table><tr><th>oracle</th><th>fired</th><th>obligation</th></tr>';
  (vd.votes||[]).forEach(o=>{{const cls=o.fired?'fail':'pass';votes+='<tr><td>'+o.oracle+'</td><td class="'+cls+'">'+(o.fired?'caught':'ok')+'</td><td>'+(o.obligation||'')+'</td></tr>';}});
  votes+='</table>';
  h+='<details><summary>'+vd.verdict_id+' — '+vd.outcome+' (tally '+vd.tally+'/'+vd.threshold+')</summary>'+votes+'</details>';
 }});
 document.getElementById('verdicts').innerHTML=h;
}})();
// Trace timeline.
(function(){{
 let h=''; DATA.events.forEach(e=>{{h+='<div class="ev"><span class="seq">#'+e.seq+'</span> <b>'+e.type+'</b> '+JSON.stringify(e.data).slice(0,160)+'</div>';}});
 document.getElementById('trace').innerHTML=h;
}})();
</script></body></html>
"""


def render_site(run_id: str) -> Path:
    data = _collect(run_id)
    arts = RunArtifacts.for_run(run_id)
    site_dir = arts.root / "site"
    site_dir.mkdir(parents=True, exist_ok=True)
    html = _TEMPLATE.format(
        run_id=run_id,
        data_json=json.dumps(data, default=str).replace("</", "<\\/"))
    out = site_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def _render_index() -> Path:
    from shared.obs.emit import artifacts_root

    rows = list_runs()
    body = "".join(
        f'<tr><td><a href="{r.get("run_id")}/site/index.html">{r.get("run_id")}</a></td>'
        f'<td>{r.get("target")}</td><td>{r.get("status")}</td>'
        f'<td>{r.get("verdicts", "-")}</td></tr>'
        for r in rows)
    html = (
        '<!doctype html><meta charset="utf-8"><title>Crucible runs</title>'
        '<style>body{font-family:ui-monospace,monospace;background:#0a0e1a;color:#e2e8f0;'
        'padding:24px}td,th{border:1px solid #2a3550;padding:6px 10px}a{color:#6366f1}</style>'
        f'<h1>Crucible runs ({len(rows)})</h1><table>'
        '<tr><th>run</th><th>target</th><th>status</th><th>verdicts</th></tr>'
        f'{body}</table>')
    out = artifacts_root() / "runs" / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def cmd_report(args: argparse.Namespace) -> int:
    if args.all:
        out = _render_index()
        print(f"rendered index: {out}")
        return 0
    run_id = args.open_run or args.run
    if not run_id:
        print("provide --run <id> or --all")
        return 2
    out = render_site(run_id)
    print(f"rendered: {out}")
    if args.open_run:
        with contextlib.suppress(OSError):
            subprocess.run(["open", str(out)], check=False)
    return 0
