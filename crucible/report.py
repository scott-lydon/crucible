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
# no numeric literal in any metric slot, so the facade-grep stays clean. Typography uses a
# sans-serif (Inter via system stack) for prose and a monospace for IDs / code / trace so
# the report reads like a report instead of a terminal dump.
_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Crucible report — {run_id}</title>
<style>
 :root{{
   --bg:#0a0e1a; --panel:#111726; --panel2:#141b2e; --border:#1f2942;
   --text:#e7ecf5; --muted:#8b95ad; --dim:#5b6584;
   --accent:#7c8cff; --accent-soft:#2a3568;
   --ok:#34d399; --warn:#fbbf24; --bad:#f87171; --info:#60a5fa;
   --mono:ui-monospace, "JetBrains Mono", "SF Mono", Menlo, monospace;
   --sans:Inter, -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
 }}
 *{{box-sizing:border-box}}
 body{{font-family:var(--sans);background:var(--bg);color:var(--text);margin:0;
   line-height:1.55;letter-spacing:-.005em;
   font-feature-settings:"ss01","cv02","cv11";
   background-image:radial-gradient(1200px 600px at 80% -10%,rgba(124,140,255,.06),transparent),
                    radial-gradient(900px 500px at -10% 110%,rgba(96,165,250,.05),transparent)}}
 .wrap{{max-width:1120px;margin:0 auto;padding:48px 32px 96px}}
 .hdr{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:6px}}
 h1{{font-size:2.1em;font-weight:700;letter-spacing:-.02em;margin:0;color:#fff}}
 h2{{font-size:1.1em;font-weight:600;letter-spacing:-.005em;color:#fff;
   margin:40px 0 12px;text-transform:none}}
 h2::before{{content:"";display:inline-block;width:3px;height:14px;background:var(--accent);
   border-radius:2px;margin-right:10px;vertical-align:middle}}
 p{{color:var(--muted);margin:.4em 0}}
 .lede{{font-size:.92em;max-width:62ch}}
 .mono,code,.id{{font-family:var(--mono);font-size:.9em}}
 .id{{color:var(--muted);background:rgba(255,255,255,.03);
   padding:2px 8px;border-radius:6px;border:1px solid var(--border)}}
 /* Status pills */
 .pillrow{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 8px}}
 .pill{{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;
   border-radius:999px;font-size:.82em;font-weight:600;letter-spacing:.01em;
   background:rgba(255,255,255,.04);border:1px solid var(--border);color:var(--text)}}
 .pill .dot{{width:7px;height:7px;border-radius:50%;background:var(--muted)}}
 .pill.ok .dot{{background:var(--ok)}} .pill.ok{{color:#a7f3d0}}
 .pill.warn .dot{{background:var(--warn)}} .pill.warn{{color:#fde68a}}
 .pill.bad .dot{{background:var(--bad)}} .pill.bad{{color:#fecaca}}
 .pill.info .dot{{background:var(--info)}} .pill.info{{color:#bfdbfe}}
 .pill .k{{color:var(--dim);font-weight:500;text-transform:uppercase;font-size:.78em;
   letter-spacing:.06em}}
 /* Metric cards */
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
   gap:12px;margin:16px 0}}
 .card{{background:linear-gradient(180deg,var(--panel) 0%,var(--panel2) 100%);
   border:1px solid var(--border);border-radius:14px;padding:18px 20px;
   position:relative;overflow:hidden}}
 .card::after{{content:"";position:absolute;left:0;right:0;top:0;height:1px;
   background:linear-gradient(90deg,transparent,rgba(255,255,255,.06),transparent)}}
 .card .v{{font-size:2.2em;font-weight:700;letter-spacing:-.03em;color:#fff;
   font-variant-numeric:tabular-nums;line-height:1.1;margin-bottom:4px}}
 .card .v.ok{{color:var(--ok)}} .card .v.warn{{color:var(--warn)}}
 .card .v.bad{{color:var(--bad)}}
 .card .l{{font-size:.82em;color:var(--muted);font-weight:500}}
 /* Tables */
 .tbl{{border:1px solid var(--border);border-radius:12px;overflow:hidden;
   margin:8px 0;background:var(--panel)}}
 table{{border-collapse:collapse;width:100%}}
 th{{text-align:left;font-size:.78em;font-weight:600;text-transform:uppercase;
   letter-spacing:.06em;color:var(--dim);padding:12px 16px;
   background:rgba(255,255,255,.02);border-bottom:1px solid var(--border)}}
 td{{padding:12px 16px;border-bottom:1px solid var(--border);font-size:.92em;
   font-variant-numeric:tabular-nums}}
 tr:last-child td{{border-bottom:none}}
 tr:hover td{{background:rgba(255,255,255,.02)}}
 td.right{{text-align:right}}
 td.mono{{font-family:var(--mono);font-size:.86em;color:var(--muted)}}
 /* Verdict cards */
 .verdicts{{display:grid;gap:10px;margin:8px 0}}
 .vd{{border:1px solid var(--border);border-radius:12px;background:var(--panel);
   overflow:hidden;transition:border-color .15s}}
 .vd:hover{{border-color:#2d3a5e}}
 .vd>summary{{list-style:none;cursor:pointer;padding:14px 16px;
   display:flex;align-items:center;gap:12px}}
 .vd>summary::-webkit-details-marker{{display:none}}
 .vd>summary::before{{content:"▸";color:var(--dim);transition:transform .15s;
   display:inline-block;font-size:.9em}}
 .vd[open]>summary::before{{transform:rotate(90deg)}}
 .vd .vid{{font-family:var(--mono);font-size:.88em;color:var(--text);flex:1}}
 .vd .tally{{font-family:var(--mono);font-size:.82em;color:var(--muted)}}
 .vd .body{{padding:4px 16px 16px;border-top:1px solid var(--border);
   background:rgba(0,0,0,.15)}}
 .vd.caught{{border-left:3px solid var(--bad)}}
 .vd.clean{{border-left:3px solid var(--ok)}}
 /* Per-vote styling */
 .pass{{color:var(--ok);font-weight:600}}
 .fail{{color:var(--bad);font-weight:600}}
 /* Trace timeline */
 .trace{{border:1px solid var(--border);border-radius:12px;background:var(--panel);
   max-height:480px;overflow-y:auto;padding:6px 0}}
 .ev{{padding:6px 16px;font-family:var(--mono);font-size:.84em;
   border-bottom:1px solid rgba(255,255,255,.03);display:flex;gap:10px}}
 .ev:last-child{{border-bottom:none}}
 .ev:hover{{background:rgba(255,255,255,.02)}}
 .seq{{color:var(--dim);min-width:36px;text-align:right}}
 .etype{{color:var(--accent);font-weight:600;min-width:160px}}
 .edata{{color:var(--muted);flex:1;overflow:hidden;text-overflow:ellipsis;
   white-space:nowrap}}
 .empty{{padding:14px 16px;color:var(--muted);font-style:italic;
   background:var(--panel);border:1px dashed var(--border);border-radius:12px}}
</style></head><body>
<div class="wrap">
 <div class="hdr">
  <h1>Crucible run</h1>
  <span class="id">{run_id}</span>
 </div>
 <p class="lede">Every number below is read directly from this run's artifact files.
 A blank metric reads <em>Not yet measured</em>, never a placeholder zero.</p>
 <div class="pillrow" id="header"></div>
 <h2>Headline metrics</h2>
 <div class="cards">
  <div class="card"><div class="v" data-metric="white_box_catch_rate" data-tone="catch"></div><div class="l">White-box catch rate</div></div>
  <div class="card"><div class="v" data-metric="black_box_catch_rate" data-tone="catch"></div><div class="l">Black-box catch rate</div></div>
  <div class="card"><div class="v" data-metric="validation_vs_holdout_gap" data-tone="gap"></div><div class="l">Black-box vs white-box gap</div></div>
  <div class="card"><div class="v" data-metric="undetected_hack_rate" data-tone="undetected"></div><div class="l">Undetected-hack rate</div></div>
  <div class="card"><div class="v" data-metric="dollars_per_caught_hack" data-tone="neutral"></div><div class="l">Cost per caught hack</div></div>
 </div>
 <h2>Co-evolution and attack success rate</h2>
 <div id="coevo"></div>
 <h2>Strategy leaderboard</h2>
 <p>Undetected tactics the red agent landed on, in discovery order.</p>
 <div id="catalog"></div>
 <h2>Verdicts</h2>
 <div id="verdicts" class="verdicts"></div>
 <h2>Trace timeline</h2>
 <div id="trace" class="trace"></div>
</div>
<script id="data" type="application/json">{data_json}</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const NM = '<span class="mono" style="color:var(--dim)">not yet measured</span>';
function pct(v){{return (v===null||v===undefined)?NM:(v*100).toFixed(1)+'%';}}
function usd(v){{return (v===null||v===undefined)?NM:'$'+Number(v).toFixed(4);}}
// Pick a tone class for a metric tile based on the value's direction. catch rates: green
// if >=0.8, amber 0.5-0.8, red <0.5. undetected rates: inverted. gap: green when low.
function metricTone(kind,v){{
 if(v===null||v===undefined) return '';
 if(kind==='catch') return v>=.8?'ok':v>=.5?'warn':'bad';
 if(kind==='undetected') return v<=.2?'ok':v<=.5?'warn':'bad';
 if(kind==='gap') return v<=.1?'ok':v<=.3?'warn':'bad';
 return '';
}}
// Status pills: eligibility + suitability with verdict-aware colors.
function pillTone(verdict){{
 const s = String(verdict||'').toUpperCase();
 if(s.includes('INELIGIBLE')||s.includes('BLOCK')) return 'bad';
 if(s.includes('CAVEAT')||s.includes('WARN')||s==='WORKABLE') return 'warn';
 if(s.includes('ELIGIBLE')||s==='IDEAL'||s==='OK') return 'ok';
 return 'info';
}}
(function(){{
 const e=DATA.eligibility, s=DATA.suitability;
 const h=document.getElementById('header'); h.innerHTML='';
 if(e){{
  const t=pillTone(e.verdict);
  h.insertAdjacentHTML('beforeend',
   '<span class="pill '+t+'"><span class="dot"></span><span class="k">Eligibility</span>'+e.verdict+'</span>');
 }}
 if(s){{
  const t=pillTone(s.grade);
  h.insertAdjacentHTML('beforeend',
   '<span class="pill '+t+'"><span class="dot"></span><span class="k">Suitability</span>'+s.grade+'</span>');
 }}
}})();
// Metric slots: filled ONLY from DATA.metrics.tiles; null/absent -> "Not yet measured".
(function(){{
 const tiles=(DATA.metrics&&DATA.metrics.tiles)||{{}};
 document.querySelectorAll('[data-metric]').forEach(el=>{{
  const k=el.getAttribute('data-metric'); const tone=el.getAttribute('data-tone');
  const v=tiles[k];
  el.innerHTML = (k==='dollars_per_caught_hack') ? usd(v) : pct(v);
  const cls = metricTone(tone,v);
  if(cls) el.classList.add(cls);
 }});
}})();
// Co-evolution / ASR curve from metric_update events that carry asr/detection.
(function(){{
 const rows=DATA.events.filter(e=>e.type==='metric_update'&&(e.data.asr!=null||e.data.detection!=null));
 const wrap=document.getElementById('coevo');
 if(!rows.length){{wrap.innerHTML='<div class="empty">No co-evolution rounds yet.</div>';return;}}
 let t='<div class="tbl"><table><tr><th>round</th><th class="right">attack success rate</th><th class="right">detection</th></tr>';
 rows.forEach((r,i)=>{{t+='<tr><td class="mono">'+(r.data.round??i)+'</td>'
   +'<td class="right">'+pct(r.data.asr)+'</td>'
   +'<td class="right">'+pct(r.data.detection)+'</td></tr>';}});
 wrap.innerHTML=t+'</table></div>';
}})();
// Strategy leaderboard from catalog.jsonl.
(function(){{
 const c=DATA.catalog; const wrap=document.getElementById('catalog');
 if(!c.length){{wrap.innerHTML='<div class="empty">No undetected tactics recorded.</div>';return;}}
 let t='<div class="tbl"><table><tr><th>#</th><th>tactic</th><th>outcome</th></tr>';
 c.forEach((r,i)=>{{const o=String(r.outcome||'').toLowerCase();
   const cls=o==='clean'?'fail':o==='caught'?'pass':'';
   t+='<tr><td class="mono">'+(i+1)+'</td>'
     +'<td>'+(r.tactic||r.attack_id||r.verdict_id||'?')+'</td>'
     +'<td class="'+cls+'">'+(r.outcome||'')+'</td></tr>';}});
 wrap.innerHTML=t+'</table></div>';
}})();
// Verdict drill-down with caught/clean color stripe.
(function(){{
 const v=DATA.verdicts; const wrap=document.getElementById('verdicts');
 if(!v.length){{wrap.innerHTML='<div class="empty">No verdicts.</div>';return;}}
 let h='';
 v.forEach(vd=>{{
  const outcome=String(vd.outcome||'').toLowerCase();
  let votes='<div class="body"><div class="tbl"><table><tr><th>oracle</th><th>verdict</th><th>obligation</th></tr>';
  (vd.votes||[]).forEach(o=>{{const cls=o.fired?'fail':'pass';
   votes+='<tr><td class="mono">'+o.oracle+'</td>'
     +'<td class="'+cls+'">'+(o.fired?'caught':'ok')+'</td>'
     +'<td>'+(o.obligation||'')+'</td></tr>';}});
  votes+='</table></div></div>';
  h+='<details class="vd '+outcome+'"><summary>'
   +'<span class="vid">'+vd.verdict_id+'</span>'
   +'<span class="pill '+(outcome==='caught'?'bad':'ok')+'"><span class="dot"></span>'+vd.outcome+'</span>'
   +'<span class="tally">tally '+vd.tally+' / '+vd.threshold+'</span>'
   +'</summary>'+votes+'</details>';
 }});
 wrap.innerHTML=h;
}})();
// Trace timeline.
(function(){{
 const wrap=document.getElementById('trace');
 if(!DATA.events.length){{wrap.innerHTML='<div class="empty">No trace events.</div>';return;}}
 let h='';
 DATA.events.forEach(e=>{{const d=JSON.stringify(e.data).slice(0,200);
  h+='<div class="ev"><span class="seq">#'+e.seq+'</span>'
    +'<span class="etype">'+e.type+'</span>'
    +'<span class="edata">'+d+'</span></div>';}});
 wrap.innerHTML=h;
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
